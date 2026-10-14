"""会话持久化测试：Checkpointer 多轮恢复、线程隔离、重启恢复。"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

from app.agent.graph import CommuteAgent
from app.agent.checkpointer import CheckpointerManager


@pytest_asyncio.fixture
async def agent_with_checkpointer(tmp_path):
    """创建带临时 SQLite Checkpointer 的 Agent。"""
    os.environ.setdefault("DEEPSEEK_API_KEY", "")  # 用规则解析，避免真实调用
    db_path = str(tmp_path / "checkpoint.db")
    mgr = CheckpointerManager(db_path)
    cp = await mgr.get_saver()
    agent = CommuteAgent(checkpointer=cp)
    yield agent
    await mgr.close()


@pytest.mark.asyncio
async def test_multiround_recovery(agent_with_checkpointer):
    """同一 thread_id 的多轮会话能恢复 commute_request。"""
    agent = agent_with_checkpointer
    r1 = await agent.ainvoke("我想去滨海湾", thread_id="s1")
    assert r1.get("needs_clarification") is True

    r2 = await agent.ainvoke("从裕廊东出发，明天8点", thread_id="s1")
    assert r2.get("needs_clarification") is False
    req = r2.get("commute_request", {})
    assert req.get("origin") == "裕廊东"
    assert req.get("destination") == "滨海湾"
    assert len(r2.get("route_scores", [])) >= 1


@pytest.mark.asyncio
async def test_thread_isolation(agent_with_checkpointer):
    """不同 thread_id 之间的状态不能混淆。"""
    agent = agent_with_checkpointer

    # 会话 A 先建立 destination
    await agent.ainvoke("我想去滨海湾", thread_id="sA")
    # 会话 B 全新开始，不应有 A 的 destination
    rB = await agent.ainvoke("我想去乌节路", thread_id="sB")
    reqB = rB.get("commute_request", {})
    assert reqB.get("destination") == "乌节路"
    assert reqB.get("origin") is None

    # 会话 A 补充 origin，destination 应是 A 自己的滨海湾
    rA = await agent.ainvoke("从裕廊东出发", thread_id="sA")
    reqA = rA.get("commute_request", {})
    assert reqA.get("destination") == "滨海湾"
    assert reqA.get("origin") == "裕廊东"


@pytest.mark.asyncio
async def test_restart_recovery(tmp_path):
    """服务重启（关闭并重新打开连接）后状态仍可恢复。"""
    os.environ.setdefault("DEEPSEEK_API_KEY", "")
    db_path = str(tmp_path / "checkpoint.db")

    # 第一段：建立会话并保存
    mgr1 = CheckpointerManager(db_path)
    cp1 = await mgr1.get_saver()
    agent1 = CommuteAgent(checkpointer=cp1)
    await agent1.ainvoke("我想去滨海湾", thread_id="persist")
    await mgr1.close()

    # 第二段：模拟重启，重新打开
    mgr2 = CheckpointerManager(db_path)
    cp2 = await mgr2.get_saver()
    agent2 = CommuteAgent(checkpointer=cp2)
    r = await agent2.ainvoke("从裕廊东出发", thread_id="persist")
    req = r.get("commute_request", {})
    assert req.get("destination") == "滨海湾"
    assert req.get("origin") == "裕廊东"
    assert len(r.get("route_scores", [])) >= 1
    await mgr2.close()


@pytest.mark.asyncio
async def test_checkpointer_sqlite_persists(tmp_path):
    """直接验证 Checkpointer 的 aput/aget 持久化。"""
    from langgraph.checkpoint.base import empty_checkpoint

    db_path = str(tmp_path / "cp.db")
    mgr = CheckpointerManager(db_path)
    cp = await mgr.get_saver()
    cfg = {"configurable": {"thread_id": "t1", "checkpoint_ns": ""}}
    await cp.aput(cfg, empty_checkpoint(), metadata={}, new_versions={})
    got = await cp.aget_tuple(cfg)
    assert got.config["configurable"]["thread_id"] == "t1"
    await mgr.close()
