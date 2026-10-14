"""Agent 工作流集成测试：解析、评分、推荐、澄清。"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

from app.agent.graph import CommuteAgent
from app.services.llm_service import MockLLMService


@pytest_asyncio.fixture
async def agent():
    """使用 Mock LLM 的 Agent（不依赖真实 API）。"""
    os.environ.setdefault("DEEPSEEK_API_KEY", "")
    return CommuteAgent(llm_service=MockLLMService())


@pytest.mark.asyncio
async def test_parse_full_commute(agent):
    r = await agent.ainvoke("我明天早上8点从裕廊东去滨海湾，少换乘")
    req = r.get("commute_request", {})
    assert req.get("origin") == "裕廊东"
    assert req.get("destination") == "滨海湾"
    assert req.get("departure_time") == "08:00"
    assert r.get("needs_clarification") is False
    assert len(r.get("route_scores", [])) >= 1


@pytest.mark.asyncio
async def test_clarification_missing_fields(agent):
    r = await agent.ainvoke("我想去滨海湾")
    assert r.get("needs_clarification") is True
    assert "origin" in r.get("missing_fields", [])


@pytest.mark.asyncio
async def test_score_and_recommendation(agent):
    r = await agent.ainvoke("我明天8点从裕廊东去滨海湾")
    scores = r.get("route_scores", [])
    assert len(scores) >= 1
    # 第一条是推荐（可行优先 + 分数降序）
    assert scores[0]["score"] >= scores[-1]["score"]
    assert r.get("final_response")
    assert r.get("selected_route") is not None


@pytest.mark.asyncio
async def test_recommendation_contains_source_tag(agent):
    r = await agent.ainvoke("我明天8点从裕廊东去滨海湾")
    assert "模拟数据" in r.get("final_response", "")


@pytest.mark.asyncio
async def test_mode_driving(agent):
    r = await agent.ainvoke("我明天8点开车从裕廊东去滨海湾")
    req = r.get("commute_request", {})
    assert req.get("mode") == "driving"


@pytest.mark.asyncio
async def test_preference_change_multi_turn(agent):
    """多轮：修改偏好后重新规划。"""
    r1 = await agent.ainvoke("我明天8点从裕廊东去滨海湾")
    assert len(r1.get("route_scores", [])) >= 1

    # 通过 state_override 模拟多轮（无 checkpointer 场景）
    r2 = await agent.ainvoke(
        "换一条少走路的路线",
        state_override={"commute_request": r1.get("commute_request")},
    )
    assert len(r2.get("route_scores", [])) >= 1


@pytest.mark.asyncio
async def test_is_mock_returns_true_for_mock_source(agent):
    """route_results.source=mock 应判定为模拟数据。"""
    assert agent._is_mock({"route_results": {"source": "mock"}}) is True
    assert agent._is_mock({"route_results": {"source": ""}}) is True
    assert agent._is_mock({"route_results": {"source": "mcp"}}) is True


@pytest.mark.asyncio
async def test_is_mock_returns_false_for_real_source(agent):
    """route_results.source=google_maps 不应判定为模拟数据。"""
    assert agent._is_mock({"route_results": {"source": "google_maps"}}) is False


@pytest.mark.asyncio
async def test_recommendation_error_source_not_marked_real(agent):
    """路线查询失败（status=error）时，回复不应标记为实时数据。"""
    state = {
        "route_results": {"status": "error", "source": "google_maps", "data": None, "error": "请求超时"},
        "route_scores": [],
        "errors": ["路线查询失败：请求超时"],
        "commute_request": {"origin": "裕廊东", "destination": "滨海湾"},
        "weather_result": {},
        "traffic_incidents": {},
    }
    await agent.generate_recommendation(state)
    resp = state.get("final_response", "")
    # 不应出现「实时数据」字样
    assert "实时数据" not in resp
    # 不应出现「Google Maps 实时路线」
    assert "Google Maps 实时路线" not in resp
