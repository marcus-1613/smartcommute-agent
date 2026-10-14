"""数据来源汇总逻辑测试：区分真实/Mock/降级/失败，不将混合源统一标为实时。"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.agent.graph import CommuteAgent
from app.services.llm_service import MockLLMService


@pytest_asyncio.fixture
async def agent():
    return CommuteAgent(llm_service=MockLLMService())


@pytest.mark.asyncio
async def test_summarize_all_mock(agent):
    state = {
        "route_results": {"source": "mock", "status": "ok"},
        "weather_result": {"source": "mock", "status": "ok"},
        "traffic_incidents": {"source": "mock", "status": "ok"},
    }
    s = agent._summarize_sources(state)
    assert s["overall"] == "mock"


@pytest.mark.asyncio
async def test_summarize_all_live(agent):
    state = {
        "route_results": {"source": "google_maps", "status": "ok"},
        "weather_result": {"source": "open_meteo", "status": "ok"},
        "traffic_incidents": {"source": "lta_datamall", "status": "ok"},
    }
    s = agent._summarize_sources(state)
    assert s["overall"] == "live"


@pytest.mark.asyncio
async def test_summarize_mixed_degraded(agent):
    """混合来源（部分真实、部分模拟、部分失败）应标记为 degraded，而非 live。"""
    state = {
        "route_results": {"source": "mock", "status": "ok"},
        "weather_result": {"source": "open_meteo", "status": "ok"},
        "traffic_incidents": {"source": "lta_datamall", "status": "error"},
    }
    s = agent._summarize_sources(state)
    assert s["overall"] == "degraded"


@pytest.mark.asyncio
async def test_summarize_all_error(agent):
    state = {
        "route_results": {"source": "google_maps", "status": "error"},
        "weather_result": {"source": "open_meteo", "status": "error"},
        "traffic_incidents": {"source": "lta_datamall", "status": "error"},
    }
    s = agent._summarize_sources(state)
    assert s["overall"] == "error"


@pytest.mark.asyncio
async def test_summarize_empty(agent):
    s = agent._summarize_sources({})
    assert s["overall"] == "mock"


@pytest.mark.asyncio
async def test_source_entry_none():
    assert CommuteAgent._source_entry(None) is None
    # 空 dict 视为无结果，返回 None（不参与汇总）
    assert CommuteAgent._source_entry({}) is None
    # 正常结果提取 source 与 status
    assert CommuteAgent._source_entry({"source": "open_meteo", "status": "ok"}) == {
        "source": "open_meteo",
        "status": "ok",
    }


@pytest.mark.asyncio
async def test_recommendation_not_live_when_mixed(agent):
    """混合来源时，最终回复不应标记为「实时数据」。"""
    state = {
        "route_results": {"source": "mock", "status": "ok", "data": {"routes": []}},
        "weather_result": {"source": "open_meteo", "status": "ok", "data": {}},
        "traffic_incidents": {"source": "lta_datamall", "status": "ok", "data": {"incidents": []}},
        "data_sources": {},
        "route_scores": [],
        "errors": [],
        "commute_request": {"origin": "裕廊东", "destination": "滨海湾"},
    }
    state["data_sources"] = agent._summarize_sources(state)
    await agent.generate_recommendation(state)
    resp = state.get("final_response", "")
    # 混合来源不应出现「实时数据」
    assert "实时数据" not in resp
