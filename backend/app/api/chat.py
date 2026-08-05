"""聊天与通勤 Agent API 路由。"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agent.graph import CommuteAgent
from ..agent.checkpointer import CheckpointerManager
from ..models.database import get_db
from ..schemas.api import ChatRequest, ChatResponse
from ..repositories import repository as repo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# 全局单例 Agent（复用已编译的图，避免频繁重建）
_agent: CommuteAgent | None = None
_checkpointer_manager: CheckpointerManager | None = None
# 进程内多轮会话兜底缓存（Checkpointer 不可用时的降级）
_session_state: Dict[str, Any] = {}


async def get_agent() -> CommuteAgent:
    """构建（或复用）全局 Agent，含 SQLite Checkpointer 持久化。"""
    global _agent, _checkpointer_manager
    if _agent is None:
        checkpointer = None
        try:
            _checkpointer_manager = CheckpointerManager()
            checkpointer = await _checkpointer_manager.get_saver()
            logger.info("Checkpointer 初始化成功（SQLite）")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Checkpointer 初始化失败，降级为进程内状态：%s", exc)
            checkpointer = None
        _agent = CommuteAgent(checkpointer=checkpointer)
    return _agent


async def shutdown_agent() -> None:
    """应用关闭时清理 Checkpointer 连接。"""
    global _checkpointer_manager
    if _checkpointer_manager is not None:
        await _checkpointer_manager.close()
        _checkpointer_manager = None


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """处理一条用户消息，执行通勤 Agent 工作流。"""
    agent = await get_agent()

    session_id = req.session_id or str(uuid.uuid4())

    # 确保会话存在
    conv = repo.get_conversation(db, session_id)
    if conv is None:
        conv = repo.create_conversation(db, session_id)

    # 记录用户消息
    repo.add_message(db, session_id, "user", req.message)

    # 记录工具调用耗时（简化：记录整体耗时）
    start = time.perf_counter()

    # 多轮会话：复用之前累积的 commute_request
    state_override = None
    if session_id in _session_state:
        state_override = {"commute_request": _session_state[session_id]}

    try:
        result = await agent.ainvoke(
            req.message,
            state_override=state_override,
            thread_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Agent 执行失败")
        repo.add_message(
            db, session_id, "assistant",
            f"系统处理出错：{exc}，请稍后重试。",
        )
        repo.log_tool_call(db, session_id, "agent", "error", str(exc))
        raise HTTPException(status_code=500, detail="Agent 执行失败") from exc

    # 缓存本次 commute_request，供后续轮次补全
    req_data = result.get("commute_request") or {}
    if req_data:
        _session_state[session_id] = req_data

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    reply = result.get("final_response", "")
    route_scores = result.get("route_scores", [])
    selected = result.get("selected_route")
    # 数据来源标识：基于 Agent 汇总的 data_sources.overall
    # 取值：mock（全部模拟）/ live（全部真实）/ degraded（部分降级）/ error（全部失败）
    data_sources = result.get("data_sources") or {}
    source = data_sources.get("overall", "mock")
    if source == "live":
        # 兼容旧字段：真实数据时，优先给出路线来源名（供历史数据展示）
        source = data_sources.get("routes", {}).get("source", "live")

    # 记录助手回复
    repo.add_message(db, session_id, "assistant", reply)

    # 保存通勤计划（若生成了路线）
    if route_scores and req_data.get("origin") and req_data.get("destination"):
        try:
            repo.create_commute_plan(
                db,
                conversation_id=session_id,
                origin=req_data["origin"],
                destination=req_data["destination"],
                departure_time=req_data.get("departure_time"),
                mode=req_data.get("mode", "transit"),
                selected_route_id=(
                    selected["route"].get("id") if selected else None
                ),
                recommendation=reply,
                source=source,
                route_scores=route_scores,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("保存通勤计划失败")
            repo.log_tool_call(
                db, session_id, "save_plan", "error", str(exc), elapsed_ms
            )

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        needs_clarification=bool(result.get("needs_clarification")),
        route_scores=route_scores,
        selected_route=selected,
        source=source,
        data_sources=data_sources,
        errors=result.get("errors", []),
    )
