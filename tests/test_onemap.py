"""OneMap Routing 适配器测试：正常响应、不同模式、认证失败、无路线、超时、畸形响应。

全部使用 mock HTTP 响应，不依赖外网。
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_servers"))

from shared.onemap_service import OneMapRoutesService


# ---------- 缺 Token / 坐标解析 ----------

def test_onemap_source_name():
    svc = OneMapRoutesService(token="")
    assert svc.source_name == "onemap"


def test_onemap_missing_token(monkeypatch):
    """缺 Token 时返回明确错误。"""
    monkeypatch.setenv("ONEMAP_TOKEN", "")
    svc = OneMapRoutesService(token="")
    r = svc.get_routes("裕廊东", "滨海湾", "transit")
    assert r["status"] == "error"
    assert "ONEMAP_TOKEN" in r["error"]


def test_onemap_search_place_known():
    """已知地点应解析为 WGS84 坐标。"""
    svc = OneMapRoutesService(token="")
    r = svc.search_place("裕廊东")
    assert r["status"] == "ok"
    assert r["data"]["coordinates"] == [1.3331, 103.7421]


def test_onemap_search_place_unknown():
    """未知地点应返回错误，不把地址字符串当坐标。"""
    svc = OneMapRoutesService(token="")
    r = svc.search_place("某个不存在的地方XYZ")
    assert r["status"] == "error"


def test_onemap_unresolvable_origin_returns_error():
    """无法解析坐标时应返回错误（不把地址当坐标传入）。"""
    svc = OneMapRoutesService(token="test-token")
    r = svc.get_routes("不存在的地方XYZ", "滨海湾", "transit")
    assert r["status"] == "error"
    assert "无法解析" in r["error"]


# ---------- 正常响应：drive ----------

def test_onemap_drive_success(monkeypatch):
    """drive 响应正确解析 route_summary + route_instructions。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "status": 200,
                "route_summary": {
                    "start_point": "1.3331,103.7421",
                    "end_point": "1.2764,103.8545",
                    "total_time": 1320,   # 秒 = 22 分钟
                    "total_distance": 18500,  # 米
                },
                "route_instructions": [
                    ["Head", "PIE", 500, "1.3331,103.7421", 30, "500m", "East", "N", "driving", "Head East on PIE"],
                    ["Right", "CTE", 300, "1.30,103.85", 20, "300m", "South", "E", "driving", "Turn right onto CTE"],
                ],
                "route_geometry": "encoded_polyline_string",
            }

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    r = svc.get_routes("裕廊东", "滨海湾", "driving")
    assert r["status"] == "ok"
    assert r["source"] == "onemap"
    routes = r["data"]["routes"]
    assert len(routes) == 1
    route = routes[0]
    assert route["duration_min"] == pytest.approx(22.0)
    assert route["distance_m"] == 18500
    assert route["mode"] == "driving"
    assert len(route["steps"]) == 2
    assert route["steps"][0]["road_name"] == "PIE"
    assert route["steps"][0]["distance_m"] == 500
    assert route["route_geometry"] == "encoded_polyline_string"


# ---------- 正常响应：pt（公交） ----------

def test_onemap_pt_success(monkeypatch):
    """pt 响应正确解析 plan.itineraries[]。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "plan": {
                    "itineraries": [
                        {
                            "duration": 2700,       # 秒 = 45 分钟
                            "walkDistance": 1197.74,
                            "transfers": 1,
                            "fare": "1.77",
                            "legs": [
                                {"mode": "WALK", "distance": 669.63,
                                 "startTime": 1762744991000, "endTime": 1762745620000,
                                 "route": "", "to": {"name": "FARRER PARK MRT"}},
                                {"mode": "SUBWAY", "distance": 12000,
                                 "startTime": 1762745620000, "endTime": 1762747000000,
                                 "route": "North East Line",
                                 "from": {"name": "FARRER PARK MRT"}, "to": {"name": "HARBOURFRONT"}},
                            ],
                        }
                    ]
                }
            }

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    r = svc.get_routes("裕廊东", "滨海湾", "transit")
    assert r["status"] == "ok"
    assert r["source"] == "onemap"
    routes = r["data"]["routes"]
    assert len(routes) == 1
    route = routes[0]
    assert route["duration_min"] == pytest.approx(45.0)
    assert route["fare_sgd"] == pytest.approx(1.77)
    assert route["walk_distance_m"] == pytest.approx(1197.74)
    assert route["transfers"] == 1
    assert len(route["steps"]) == 2
    assert route["steps"][1]["line"] == "North East Line"


# ---------- 不同交通模式 ----------

@pytest.mark.parametrize("mode,route_type", [
    ("transit", "pt"),
    ("driving", "drive"),
    ("walk", "walk"),
    ("cycling", "cycle"),
])
def test_onemap_mode_mapping(mode, route_type, monkeypatch):
    """不同模式映射到正确的 routeType 参数。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")
    captured = {}

    class _FakeResp:
        status_code = 200

        def json(self):
            # 根据 routeType 返回对应结构，避免解析崩溃
            if captured["route_type"] == "pt":
                return {"plan": {"itineraries": []}}
            return {
                "route_summary": {"total_time": 600, "total_distance": 1000},
                "route_instructions": [],
            }

    def _fake_get(url, **kwargs):
        captured["route_type"] = kwargs["params"]["routeType"]
        return _FakeResp()

    monkeypatch.setattr(httpx, "get", _fake_get)
    svc.get_routes("裕廊东", "滨海湾", mode)
    assert captured["route_type"] == route_type


# ---------- 认证失败 / 无路线 / 超时 / 畸形响应 ----------

def test_onemap_auth_failure(monkeypatch):
    """401/403 应返回认证失败错误。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")

    class _FakeResp:
        status_code = 401

        def json(self):
            return {}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    r = svc.get_routes("裕廊东", "滨海湾", "driving")
    assert r["status"] == "error"
    assert r["source"] == "onemap"
    assert "认证失败" in r["error"]


def test_onemap_no_route(monkeypatch):
    """404 应返回无可用路线错误。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")

    class _FakeResp:
        status_code = 404

        def json(self):
            return {}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    r = svc.get_routes("裕廊东", "滨海湾", "driving")
    assert r["status"] == "error"
    assert "无可用路线" in r["error"]


def test_onemap_timeout(monkeypatch):
    """请求超时应返回明确错误，不抛异常。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")

    def _raise_timeout(*a, **k):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx, "get", _raise_timeout)
    r = svc.get_routes("裕廊东", "滨海湾", "driving")
    assert r["status"] == "error"
    assert "超时" in r["error"]


def test_onemap_http_error(monkeypatch):
    """HTTP 非 200 响应应返回明确错误。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")

    class _FakeResp:
        status_code = 500

        def json(self):
            return {}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    r = svc.get_routes("裕廊东", "滨海湾", "driving")
    assert r["status"] == "error"
    assert "500" in r["error"]


def test_onemap_malformed_response(monkeypatch):
    """畸形/空响应应容错，不抛异常。"""
    import httpx

    svc = OneMapRoutesService(token="test-token")

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"unexpected": "structure"}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    r = svc.get_routes("裕廊东", "滨海湾", "driving")
    # 无有效路线 -> 返回 error（无可用路线），而非崩溃
    assert r["status"] == "error"


def test_onemap_traffic_empty():
    """OneMap Routing 不提供交通事件，返回明确空结果。"""
    svc = OneMapRoutesService(token="")
    r = svc.get_traffic_incidents()
    assert r["status"] == "ok"
    assert r["data"]["incidents"] == []


# ---------- 单位转换辅助 ----------

def test_onemap_seconds_to_minutes():
    assert OneMapRoutesService._seconds_to_minutes(1320) == pytest.approx(22.0)
    assert OneMapRoutesService._seconds_to_minutes(None) is None
    assert OneMapRoutesService._seconds_to_minutes("bad") is None


def test_onemap_fare_sgd():
    assert OneMapRoutesService._fare_sgd("1.77") == pytest.approx(1.77)
    assert OneMapRoutesService._fare_sgd(None) is None
    assert OneMapRoutesService._fare_sgd("invalid") is None
