"""MCP Server 工具测试。"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_servers"))


def test_mobility_tools_exposed():
    from mobility_server import mcp
    tools = [t.name for t in mcp._tool_manager.list_tools()]
    assert "search_place" in tools
    assert "get_routes" in tools
    assert "get_traffic_incidents" in tools


def test_weather_tools_exposed():
    from weather_server import mcp
    tools = [t.name for t in mcp._tool_manager.list_tools()]
    assert "get_weather_forecast" in tools
    assert "check_weather_risk" in tools


def test_mock_search_place_known():
    from shared.mock_mobility import MockMobilityService
    svc = MockMobilityService()
    r = svc.search_place("Jurong East")
    assert r["status"] == "ok"
    assert r["data"]["name"] == "裕廊东"
    assert r["source"] == "mock"


def test_mock_search_place_unknown():
    from shared.mock_mobility import MockMobilityService
    svc = MockMobilityService()
    r = svc.search_place("不存在的某地XYZ")
    assert r["status"] == "error"
    assert r["error"]


def test_mock_get_routes():
    from shared.mock_mobility import MockMobilityService
    svc = MockMobilityService()
    r = svc.get_routes("裕廊东", "滨海湾", "transit")
    assert r["status"] == "ok"
    assert len(r["data"]["routes"]) >= 1
    for route in r["data"]["routes"]:
        assert "duration_min" in route
        assert "transfers" in route


def test_mock_weather_risk():
    from shared.mock_weather import MockWeatherService
    svc = MockWeatherService()
    r = svc.check_weather_risk("滨海湾")
    assert r["status"] == "ok"
    assert r["data"]["risk_level"] in ("low", "medium", "high")
    assert r["data"]["advice"]
