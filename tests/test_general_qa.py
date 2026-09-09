"""非通勤问题（一般知识 / 问候 / 闲聊）分流与降级测试。

使用可注入的 Fake LLM 服务模拟不同返回结构，验证：
- 一般问题走 free_text 回答，不再返回空白。
- 模型空内容 / 调用失败时返回明确提示。
- 通勤问题仍走原流程。
- 澄清场景返回可展示文本。
"""
from __future__ import annotations

import pytest

from app.agent.graph import CommuteAgent


class FakeLLM:
    """可配置行为的最小 LLM 替身，实现 graph 需要的全部方法。"""

    source_name = "fake"

    def __init__(self, intent="commute", free_text=None, free_ok=True, parse_data=None):
        self.intent = intent
        self._free_text = free_text
        self.free_ok = free_ok
        self.parse_data = parse_data or {}

    def classify_intent(self, user_input: str, context=None):
        return {"intent": self.intent, "source": self.source_name, "error": ""}

    def chat_free_text(self, user_input: str):
        if not self.free_ok:
            return {"ok": False, "text": "", "source": self.source_name, "error": "模型超时"}
        return {
            "ok": True,
            "text": self._free_text if self._free_text is not None else "这是一段回答",
            "source": self.source_name,
            "error": "",
        }

    def parse_commute(self, user_input: str, existing=None):
        # 返回 ok=False，让 graph 走规则解析
        return {"ok": False, "data": existing or {}, "source": self.source_name, "error": ""}

    def explain_recommendation(self, context):
        return {"ok": False, "text": "", "source": self.source_name, "error": ""}


@pytest.mark.asyncio
async def test_general_question_answered_directly():
    """一般知识问题：应直接生成回答，不返回空白。"""
    agent = CommuteAgent(
        llm_service=FakeLLM(intent="general", free_text="LangGraph 是一个用于构建有状态多智能体应用的框架。")
    )
    r = await agent.ainvoke("什么是 LangGraph？")
    assert r.get("intent") == "general"
    assert r.get("final_response")  # 非空
    assert "LangGraph" in r.get("final_response", "")


@pytest.mark.asyncio
async def test_greeting_answered():
    """普通问候：应有回复。"""
    agent = CommuteAgent(llm_service=FakeLLM(intent="general", free_text="你好！我可以帮你规划新加坡的通勤路线。"))
    r = await agent.ainvoke("你好")
    assert r.get("intent") == "general"
    assert r.get("final_response")


@pytest.mark.asyncio
async def test_general_question_empty_content_has_prompt():
    """模型返回空内容：应返回明确提示，而非空白。"""
    agent = CommuteAgent(llm_service=FakeLLM(intent="general", free_text="", free_ok=True))
    r = await agent.ainvoke("什么是 LangGraph？")
    # chat_free_text 对空 text 应判为 not ok -> 走降级提示
    assert r.get("final_response")


@pytest.mark.asyncio
async def test_general_question_llm_failure_has_prompt():
    """模型调用失败：应返回明确提示，而非空白。"""
    agent = CommuteAgent(llm_service=FakeLLM(intent="general", free_ok=False))
    r = await agent.ainvoke("什么是 LangGraph？")
    resp = r.get("final_response", "")
    assert resp  # 非空
    assert "暂时无法回答" in resp


@pytest.mark.asyncio
async def test_commute_question_still_uses_workflow():
    """通勤问题仍走原流程（解析→评分→推荐），不受分流影响。"""
    agent = CommuteAgent(llm_service=FakeLLM(intent="commute"))
    r = await agent.ainvoke("我明天8点从裕廊东去滨海湾")
    assert r.get("intent") == "commute"
    assert len(r.get("route_scores", [])) >= 1
    assert r.get("final_response")


@pytest.mark.asyncio
async def test_clarify_returns_question_not_empty():
    """澄清场景：缺失字段时应返回澄清问题文本（由 chat.py 兜底展示）。"""
    agent = CommuteAgent(llm_service=FakeLLM(intent="commute"))
    r = await agent.ainvoke("我想去滨海湾")
    assert r.get("needs_clarification") is True
    # 走 clarify 分支时 final_response 为空，但 clarification_question 必须有
    assert r.get("clarification_question")


class ScriptedIntentLLM(FakeLLM):
    """根据输入内容决定意图的替身，模拟真实分类器区分话题跳转。"""

    def classify_intent(self, user_input: str, context=None):
        # 含"agent/概念/是什么"等视为一般问题（话题跳转），否则 commute
        if any(k in user_input for k in ("agent", "是什么", "概念", "你好")):
            return {"intent": "general", "source": self.source_name, "error": ""}
        return {"intent": "commute", "source": self.source_name, "error": ""}


@pytest.mark.asyncio
async def test_topic_switch_after_commute_context_is_answered():
    """多轮：通勤上下文建立后，追问一般问题应走 free_text，而非重复路线推荐。"""
    llm = ScriptedIntentLLM(free_text="Agent 是指能够在环境中自主行动、感知并做出决策的智能体。")
    agent = CommuteAgent(llm_service=llm)

    # 第一轮：建立通勤上下文
    r1 = await agent.ainvoke("我明天8点从裕廊东去滨海湾")
    assert len(r1.get("route_scores", [])) >= 1

    # 第二轮：携带已有上下文追问一般问题 → 应识别为 general
    r2 = await agent.ainvoke(
        "agent的概念是什么？",
        state_override={"commute_request": r1.get("commute_request")},
    )
    assert r2.get("intent") == "general"
    assert "Agent" in r2.get("final_response", "")
    # 不应再次生成路线推荐
    assert len(r2.get("route_scores", [])) == 0


@pytest.mark.asyncio
async def test_route_adjustment_after_commute_context_stays_commute():
    """多轮：通勤上下文后做路线调整，仍应识别为 commute（不误判为 general）。"""
    llm = ScriptedIntentLLM()
    agent = CommuteAgent(llm_service=llm)
    r1 = await agent.ainvoke("我明天8点从裕廊东去滨海湾")
    r2 = await agent.ainvoke(
        "换一条少走路的路线",
        state_override={"commute_request": r1.get("commute_request")},
    )
    assert r2.get("intent") == "commute"
    assert len(r2.get("route_scores", [])) >= 1

