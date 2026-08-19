"""LangGraph 工作流节点与图构建。

工作流：
解析需求 -> (条件) 缺失字段? -> 澄清 | 查询数据(并行) -> 规范化 ->
路线评分 -> 生成推荐 -> 返回

若已存在完整的 commute_request（多轮对话补充后），可跳过解析与澄清。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from langgraph.graph import END, StateGraph

from .state import AgentState, CommuteRequest
from ..services.mcp_client import MCPToolClient
from ..services.route_scoring import score_routes, UserPreferences
from ..services.llm_service import LLMService, build_llm_service

logger = logging.getLogger(__name__)


class CommuteAgent:
    """通勤 Agent：封装 LangGraph 工作流的编译与调用。"""

    def __init__(
        self,
        mcp_client: Optional[MCPToolClient] = None,
        checkpointer: Optional[Any] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self.mcp = mcp_client or MCPToolClient()
        self.checkpointer = checkpointer
        self.llm = llm_service or build_llm_service()
        self.graph = self._build_graph()

    # ---------- 节点实现 ----------

    async def parse_request(self, state: AgentState) -> AgentState:
        """解析用户自然语言输入，提取通勤需求字段。

        优先使用 DeepSeek 真实模型解析（结构化 JSON 输出），
        失败或未配置时降级为确定性规则解析。
        """
        user_input = state.get("user_input", "")
        existing = state.get("commute_request") or {}

        # 1) 先尝试 LLM 解析
        llm_result = await self._llm_parse(user_input, existing)
        if llm_result.get("ok") and llm_result.get("data"):
            req = llm_result["data"]
            # 确保硬约束与偏好也反映到规则层可识别的字段
            self._normalize_llm_request(req)
            state["commute_request"] = req
            state["llm_source"] = llm_result.get("source", "mock")
            return state

        # 2) 规则兜底解析
        req: CommuteRequest = dict(existing)  # 保留已有字段（多轮补充）
        self._rule_parse(user_input, req)
        state["commute_request"] = req
        state["llm_source"] = "mock"
        return state

    async def detect_intent(self, state: AgentState) -> AgentState:
        """识别用户意图：通勤/交通 或 一般问题。

        一般问题（知识、问候、闲聊等）直接由 DeepSeek 生成文本回答，
        不进入路线查询流程，避免因缺失 origin/destination 而返回空白。

        始终执行意图识别（不因已有通勤上下文而短路），并传入上下文，
        让分类器区分「路线调整/补充」（commute）与「话题跳转」（general）。
        """
        user_input = state.get("user_input", "")
        existing = state.get("commute_request") or {}

        try:
            cls = self.llm.classify_intent(user_input, context=existing)
        except Exception as exc:  # noqa: BLE001
            logger.warning("意图识别异常：%s", exc)
            cls = {"intent": "commute", "error": str(exc)}

        intent = cls.get("intent", "commute")
        # 兜底：仅当分类器异常且已有通勤上下文时，才默认按通勤处理，
        # 避免破坏多轮补充（如"换一条少走路的路线"）。
        if cls.get("error") and existing.get("origin") and existing.get("destination"):
            intent = "commute"

        state["intent"] = intent

        if intent != "commute":
            # 一般问题：直接生成回答
            try:
                ans = self.llm.chat_free_text(user_input)
            except Exception as exc:  # noqa: BLE001
                logger.warning("通用问答异常：%s", exc)
                ans = {"ok": False, "text": "", "error": str(exc)}
            if ans.get("ok") and ans.get("text"):
                state["final_response"] = ans["text"]
                state["data_sources"] = {"overall": "live"}
            else:
                # 明确降级提示，绝不返回空白
                state["final_response"] = (
                    "抱歉，我暂时无法回答这个问题。"
                    + (f"（原因：{ans.get('error')}）" if ans.get("error") else "")
                )
                state["data_sources"] = {"overall": "error"}
        return state

    async def _llm_parse(self, user_input: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        """调用 LLM 解析，返回统一结构。"""
        try:
            return self.llm.parse_commute(user_input, existing)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 解析异常，降级规则解析：%s", exc)
            return {"ok": False, "data": existing, "source": "mock", "error": str(exc)}

    def _normalize_llm_request(self, req: Dict[str, Any]) -> None:
        """规范化 LLM 返回的字段，补充规则层依赖的默认值。"""
        if not req.get("mode"):
            req["mode"] = "transit"
        # 将 preferences 里的关键词转为硬约束（若 LLM 未显式给出）
        constraints = dict(req.get("hard_constraints") or {})
        pref = req.get("preferences", "") or ""
        if "少换乘" in pref and "max_transfers" not in constraints:
            constraints["max_transfers"] = 1
        if ("少走路" in pref or "少步行" in pref) and "max_walk_m" not in constraints:
            constraints["max_walk_m"] = 800
        if constraints:
            req["hard_constraints"] = constraints

    def _rule_parse(self, user_input: str, req: CommuteRequest) -> None:
        """确定性规则解析（兜底）。"""
        import re

        time_match = re.search(r"(\d{1,2})\s*[点:：]\s*(\d{1,2})?", user_input)
        if time_match and not req.get("departure_time"):
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            req["departure_time"] = f"{hour:02d}:{minute:02d}"

        route_match = re.search(r"从\s*(.+?)\s*(?:去|到|前往)\s*(.+)", user_input)
        if route_match:
            if not req.get("origin"):
                req["origin"] = route_match.group(1).strip()
            if not req.get("destination"):
                dest = route_match.group(2).strip()
                dest = re.split(r"[，,]\s*(?:少换乘|换乘少|少走路|少步行|别走太多路|尽量|希望|最好)", dest)[0].strip()
                req["destination"] = dest

        origin_only = re.search(
            r"(?:从|在)\s*(.+?)\s*(?:出发|走|上车)", user_input
        )
        if origin_only and not req.get("origin") and not route_match:
            req["origin"] = origin_only.group(1).strip()

        dest_only = re.search(r"(?:去|到|前往)\s*(.+)", user_input)
        if dest_only and not req.get("destination") and not route_match:
            dest = dest_only.group(1).strip()
            # 去除偏好后缀（如 "，少换乘"）
            dest = re.split(r"[，,]\s*(?:少换乘|换乘少|少走路|少步行|别走太多路|尽量|希望|最好)", dest)[0].strip()
            req["destination"] = dest

        if "驾车" in user_input or "开车" in user_input:
            req["mode"] = "driving"
        elif not req.get("mode"):
            req["mode"] = "transit"

        if "少换乘" in user_input or "换乘少" in user_input:
            req["preferences"] = "少换乘"
        elif "少走路" in user_input or "少步行" in user_input or "走太多路" in user_input:
            req["preferences"] = "少步行"

        constraints: Dict[str, Any] = dict(req.get("hard_constraints") or {})
        if "少换乘" in user_input or "换乘少" in user_input:
            constraints["max_transfers"] = 1
        if "少走路" in user_input or "少步行" in user_input:
            constraints["max_walk_m"] = 800
        if constraints:
            req["hard_constraints"] = constraints

    async def check_missing(self, state: AgentState) -> AgentState:
        """检查缺失的必要字段。"""
        req = state.get("commute_request") or {}
        missing: List[str] = []
        if not req.get("origin"):
            missing.append("origin")
        if not req.get("destination"):
            missing.append("destination")
        state["missing_fields"] = missing
        state["needs_clarification"] = len(missing) > 0

        if missing:
            state["clarification_question"] = self._build_clarify_question(missing)
        return state

    def _build_clarify_question(self, missing: List[str]) -> str:
        """生成澄清问题。"""
        label_map = {"origin": "出发地", "destination": "目的地"}
        labels = "、".join(label_map[m] for m in missing)
        return f"为了帮您规划路线，请补充以下信息：{labels}。"

    async def query_data(self, state: AgentState) -> AgentState:
        """并行查询路线、天气、交通事件。"""
        req = state.get("commute_request") or {}
        origin = req.get("origin", "")
        destination = req.get("destination", "")
        mode = req.get("mode", "transit")
        departure_time = req.get("departure_time")

        # 并行调用（独立的外部查询）
        import asyncio

        routes_task = asyncio.create_task(
            self.mcp.get_routes(origin, destination, mode, departure_time)
        )
        weather_task = asyncio.create_task(
            self.mcp.check_weather_risk(destination, departure_time)
        )
        traffic_task = asyncio.create_task(
            self.mcp.get_traffic_incidents(origin)
        )

        state["route_results"] = await routes_task
        state["weather_result"] = await weather_task
        state["traffic_incidents"] = await traffic_task
        return state

    async def normalize_data(self, state: AgentState) -> AgentState:
        """规范化外部数据，识别部分失败，并汇总各数据来源状态。"""
        errors = list(state.get("errors") or [])

        route_results = state.get("route_results")
        if not route_results or route_results.get("status") == "error":
            errors.append(f"路线查询失败：{route_results.get('error') if route_results else '无结果'}")
            state["route_results"] = {"status": "error", "data": None, "error": "路线查询失败"}
        elif route_results.get("status") == "partial":
            errors.append("路线数据部分缺失")

        weather = state.get("weather_result")
        if weather and weather.get("status") == "error":
            errors.append(f"天气查询失败：{weather.get('error')}")

        traffic = state.get("traffic_incidents")
        if traffic and traffic.get("status") == "error":
            errors.append(f"交通事件查询失败：{traffic.get('error')}")

        state["errors"] = errors

        # 汇总各数据来源状态（真实 / 模拟 / 失败），供后端整体标记与前端展示
        state["data_sources"] = self._summarize_sources(state)
        return state

    def _summarize_sources(self, state: AgentState) -> Dict[str, Any]:
        """汇总各数据源的来源标识与获取状态。

        每个数据源分别记录：source（来源名）与 status（ok/partial/error）。
        规则：
        - source 为 "mock" 表示模拟数据
        - source 为真实来源名（如 google_maps/open_meteo/lta_datamall）且 status=ok 表示真实数据
        - status=error 表示真实调用失败（不冒充真实，也不冒充 mock）
        顶层汇总字段：
        - overall: "mock"（全部模拟）| "live"（全部真实）| "degraded"（部分真实/部分失败）| "error"（全部失败）
        """
        route_results = state.get("route_results") or {}
        weather = state.get("weather_result") or {}
        traffic = state.get("traffic_incidents") or {}

        sources = {
            "routes": self._source_entry(route_results),
            "weather": self._source_entry(weather),
            "traffic": self._source_entry(traffic),
        }

        # 只统计实际参与的数据源（route_results 可能为空当无需路线时）
        entries = [e for e in sources.values() if e is not None]
        statuses = [e["status"] for e in entries]
        src_names = [e["source"] for e in entries]

        if not entries:
            overall = "mock"
        elif all(s == "mock" for s in src_names):
            overall = "mock"
        elif all(s == "ok" for s in statuses) and all(
            s != "mock" for s in src_names
        ):
            overall = "live"
        elif all(s == "error" for s in statuses):
            overall = "error"
        else:
            # 混合：部分真实、部分模拟、部分失败
            overall = "degraded"

        sources["overall"] = overall
        return sources

    @staticmethod
    def _source_entry(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """从单个结果提取 {source, status}；结果为空时返回 None。"""
        if not result:
            return None
        source = result.get("source", "") or "mock"
        status = result.get("status", "error")
        return {"source": source, "status": status}

    async def score(self, state: AgentState) -> AgentState:
        """对路线进行确定性评分。"""
        req = state.get("commute_request") or {}
        route_results = state.get("route_results") or {}
        data = route_results.get("data") or {}
        routes = data.get("routes", []) if isinstance(data, dict) else []

        weather = state.get("weather_result") or {}
        weather_data = weather.get("data") or {}
        risk_level = weather_data.get("risk_level") if isinstance(weather_data, dict) else None

        traffic = state.get("traffic_incidents") or {}
        traffic_data = traffic.get("data") or {}
        incidents = traffic_data.get("incidents", []) if isinstance(traffic_data, dict) else []

        # 构建用户偏好
        prefs = UserPreferences()
        pref_text = req.get("preferences", "")
        if "少换乘" in (pref_text or ""):
            prefs.prefer_fewer_transfers = 0.9
        if "少步行" in (pref_text or ""):
            prefs.prefer_less_walking = 0.9

        constraints = req.get("hard_constraints") or {}

        scored = score_routes(
            routes,
            weather_risk_level=risk_level,
            traffic_incidents=incidents,
            preferences=prefs,
            hard_constraints=constraints,
        )

        state["route_scores"] = scored
        if scored:
            state["selected_route"] = scored[0]
        return state

    async def generate_recommendation(self, state: AgentState) -> AgentState:
        """生成最终推荐回复（含中文解释）。

        优先使用 DeepSeek 生成解释，失败则用确定性模板。
        """
        scored = state.get("route_scores") or []
        errors = state.get("errors") or []
        req = state.get("commute_request") or {}

        if not scored:
            state["final_response"] = (
                "很抱歉，未能找到可行的通勤路线。"
                + ("原因：" + "；".join(errors) if errors else "")
                + " 建议您检查出发地和目的地是否准确，或尝试调整出发时间。"
            )
            return state

        top = scored[0]
        route = top["route"]
        feasible_routes = [s for s in scored if s["feasible"]]

        # 数据来源标识：基于汇总后的整体状态区分
        # 「模拟数据」「实时数据」「部分数据」「数据不可用」
        overall = (state.get("data_sources") or {}).get("overall", "mock")
        source_label_map = {
            "mock": "模拟数据",
            "live": "实时数据",
            "degraded": "部分数据（部分来源不可用）",
            "error": "数据不可用",
        }
        source_label = source_label_map.get(overall, "模拟数据")

        # 尝试 LLM 生成解释
        llm_text = None
        llm_ok = False
        try:
            context = {
                "top_route": {
                    "summary": route.get("summary", ""),
                    "duration_min": route.get("duration_min"),
                    "fare_sgd": route.get("fare_sgd"),
                    "walk_distance_m": route.get("walk_distance_m"),
                    "transfers": route.get("transfers"),
                },
                "score": top.get("score"),
                "score_detail": top.get("score_detail", {}),
                "feasible": top.get("feasible"),
                "constraint_violations": top.get("constraint_violations", []),
                "weather_advice": (state.get("weather_result") or {}).get("data", {}).get("advice") if isinstance((state.get("weather_result") or {}).get("data"), dict) else None,
                "data_source": source_label,
            }
            explain = self.llm.explain_recommendation(context)
            if explain.get("ok") and explain.get("text"):
                llm_text = explain["text"]
                llm_ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 解释生成异常，降级模板：%s", exc)

        # 组装回复
        lines = []
        if llm_ok and llm_text:
            lines.append(llm_text)
        else:
            # 模板兜底
            if top["feasible"]:
                lines.append(
                    f"为您推荐：{route.get('summary', '最佳路线')}，"
                    f"预计耗时 {route.get('duration_min')} 分钟，"
                    f"费用约 S${route.get('fare_sgd')}，"
                    f"步行 {route.get('walk_distance_m')} 米，"
                    f"换乘 {route.get('transfers')} 次。"
                )
                reasons = self._explain_reasons(top)
                lines.append("推荐理由：" + "；".join(reasons))
            else:
                violations = top["constraint_violations"]
                lines.append("没有完全满足您所有限制的路线。")
                if violations:
                    lines.append("首选路线的限制冲突：" + "；".join(violations))
                if len(feasible_routes) > 0:
                    alt = feasible_routes[0]["route"]
                    lines.append(
                        f"建议替代方案：{alt.get('summary')}，"
                        f"耗时 {alt.get('duration_min')} 分钟，换乘 {alt.get('transfers')} 次。"
                    )

        # 天气提示（LLM 未包含时补充）
        weather = state.get("weather_result") or {}
        weather_data = weather.get("data") or {}
        if isinstance(weather_data, dict) and weather_data.get("advice"):
            advice = weather_data["advice"]
            # 避免与 LLM 解释重复
            if not (llm_text and "阵雨" in llm_text and "伞" in llm_text):
                lines.append(f"天气提示：{advice}")

        # 数据来源标识：区分「模拟」「实时」「部分模拟/部分失败」「不可用」
        if source_label == "模拟数据":
            lines.append("（当前为模拟数据演示模式，数据仅供参考）")
        elif source_label == "实时数据":
            lines.append("（数据来源：实时 API）")
        elif source_label.startswith("部分数据"):
            lines.append(self._build_partial_source_hint(state))
        else:
            lines.append("（路线数据暂不可用，请稍后重试）")

        state["final_response"] = "\n".join(lines)
        return state

    def _build_partial_source_hint(self, state: AgentState) -> str:
        """根据各数据源实际状态，生成准确的部分数据提示。

        区分「模拟数据」与「调用失败」两种降级原因，避免把
        mock 误描述为「不可用」，也不把失败误描述为「模拟」。
        """
        sources = (state.get("data_sources") or {}).copy()
        sources.pop("overall", None)
        label = {"routes": "路线", "weather": "天气", "traffic": "交通事件"}

        mock_parts = []
        failed_parts = []
        for key, entry in sources.items():
            if not entry:
                continue
            name = label.get(key, key)
            if entry.get("status") == "error":
                failed_parts.append(name)
            elif entry.get("source") == "mock":
                mock_parts.append(name)

        hints = []
        if mock_parts:
            hints.append("、".join(mock_parts) + "为模拟数据")
        if failed_parts:
            hints.append("、".join(failed_parts) + "暂不可用")
        if not hints:
            return "（部分数据来源不可用，结果可能不完整）"
        return "（" + "；".join(hints) + "，结果可能不完整）"

    def _explain_reasons(self, scored: Dict[str, Any]) -> List[str]:
        """基于评分明细生成可解释的推荐理由。"""
        detail = scored.get("score_detail", {})
        reasons = []
        if detail.get("duration", 0) > 0.7:
            reasons.append("耗时较短")
        if detail.get("fare", 0) > 0.7:
            reasons.append("费用较低")
        if detail.get("walking", 0) > 0.7:
            reasons.append("步行距离短")
        if detail.get("transfers", 0) > 0.7:
            reasons.append("换乘次数少")
        if not reasons:
            reasons.append("综合各项指标较为均衡")
        return reasons

    def _is_mock(self, state: AgentState) -> bool:
        """判断当前数据是否为模拟数据。

        仅当数据来源明确为 "mock"（或空，即无数据）时视为模拟/演示数据。
        真实来源（如 "google_maps"）或查询失败（status=error）均不应
        被当作模拟数据，也不应被当作真实数据。
        """
        route_results = state.get("route_results") or {}
        source = route_results.get("source", "")
        return source in ("mock", "", "mcp")

    # ---------- 图构建 ----------

    def _build_graph(self):
        graph = StateGraph(AgentState)

        graph.add_node("parse_request", self.parse_request)
        graph.add_node("detect_intent", self.detect_intent)
        graph.add_node("check_missing", self.check_missing)
        graph.add_node("query_data", self.query_data)
        graph.add_node("normalize_data", self.normalize_data)
        graph.add_node("score", self.score)
        graph.add_node("generate_recommendation", self.generate_recommendation)

        graph.set_entry_point("parse_request")
        graph.add_edge("parse_request", "detect_intent")

        # 条件边：一般问题直接结束（已生成回答），通勤问题进入字段检查
        graph.add_conditional_edges(
            "detect_intent",
            self._route_after_intent,
            {
                "answer": END,
                "check": "check_missing",
            },
        )

        # 条件边：缺失字段则直接返回澄清，否则进入数据查询
        graph.add_conditional_edges(
            "check_missing",
            self._route_after_check,
            {
                "clarify": END,
                "query": "query_data",
            },
        )

        graph.add_edge("query_data", "normalize_data")
        graph.add_edge("normalize_data", "score")
        graph.add_edge("score", "generate_recommendation")
        graph.add_edge("generate_recommendation", END)

        if self.checkpointer is not None:
            return graph.compile(checkpointer=self.checkpointer)
        return graph.compile()

    def _route_after_intent(self, state: AgentState) -> Literal["answer", "check"]:
        if state.get("intent") != "commute":
            return "answer"
        return "check"

    def _route_after_check(self, state: AgentState) -> Literal["clarify", "query"]:
        if state.get("needs_clarification"):
            return "clarify"
        return "query"

    # ---------- 对外调用 ----------

    async def ainvoke(
        self,
        user_input: str,
        state_override: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行一次工作流调用，返回最终状态。

        thread_id 用于多轮会话：同一 thread_id 会复用已保存的 commute_request，
        从而支持澄清后补充信息（如"我提前半小时出发"）时的增量更新。
        """
        initial: AgentState = {
            "user_input": user_input,
            "messages": [],
            "commute_request": {},
            "intent": "commute",
            "missing_fields": [],
            "needs_clarification": False,
            "clarification_question": "",
            "route_results": None,
            "weather_result": None,
            "traffic_incidents": None,
            "data_sources": {},
            "route_scores": [],
            "selected_route": None,
            "final_response": "",
            "llm_source": "mock",
            "retry_count": 0,
            "errors": [],
        }
        if state_override:
            initial.update(state_override)

        config: Dict[str, Any] = {}
        if thread_id and self.checkpointer is not None:
            config["configurable"] = {"thread_id": thread_id, "checkpoint_ns": ""}
            # 从 Checkpointer 恢复上一轮的 commute_request，实现真正的多轮会话
            try:
                prev = await self.checkpointer.aget_tuple(config)
                if prev and prev.checkpoint:
                    prev_request = prev.checkpoint.get("channel_values", {}).get(
                        "commute_request"
                    )
                    if prev_request:
                        merged = dict(prev_request)
                        if state_override and state_override.get("commute_request"):
                            merged.update(state_override["commute_request"])
                        initial["commute_request"] = merged
            except Exception as exc:  # noqa: BLE001
                logger.warning("从 Checkpointer 恢复状态失败：%s", exc)

        result = await self.graph.ainvoke(initial, config=config or None)
        return result
