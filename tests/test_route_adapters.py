"""路线服务适配器测试：Mock/真实切换、缺 Key、超时、错误、数据转换。"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_servers"))

from shared.mock_mobility import MockMobilityService
from shared.google_maps_service import GoogleMapsRoutesService


def test_mock_service_source():
    svc = MockMobilityService()
    r = svc.search_place("Jurong East")
    assert r["source"] == "mock"


def test_google_maps_missing_key(monkeypatch):
    """缺 Key 时返回明确错误。"""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    svc = GoogleMapsRoutesService(api_key="")
    r = svc.get_routes("裕廊东", "滨海湾", "transit")
    assert r["status"] == "error"
    assert "GOOGLE_MAPS_API_KEY" in r["error"]


def test_google_maps_convert_routes():
    """数据转换逻辑正确。"""
    svc = GoogleMapsRoutesService(api_key="")
    payload = {
        "routes": [
            {
                "description": "经由东西线的路线",
                "duration": "2700s",
                "transitFare": {"currencyCode": "SGD", "units": "190"},
                "legs": [
                    {"steps": [
                        {"travelMode": "WALK", "distanceMeters": 300, "duration": "240s"},
                        {"travelMode": "TRANSIT", "duration": "1500s",
                         "transitDetails": {"transitLine": {"name": "EWL", "nameShort": "EWL"}}},
                        {"travelMode": "WALK", "distanceMeters": 400, "duration": "300s"},
                    ]}
                ],
            }
        ]
    }
    routes = svc._convert_routes(payload, "transit")
    assert len(routes) == 1
    r = routes[0]
    assert r["duration_min"] == pytest.approx(45.0)
    assert r["fare_sgd"] == pytest.approx(1.9)
    assert r["walk_distance_m"] == 700
    assert r["transfers"] == 0
    assert len(r["steps"]) == 3
    assert r["steps"][1]["line"] == "EWL"


def test_google_maps_timeout(monkeypatch):
    """请求超时应返回明确错误，不抛异常。"""
    import httpx

    svc = GoogleMapsRoutesService(api_key="test-key", timeout=0.001)
    # 用极短超时 + 不可达地址模拟超时
    svc.endpoint = "http://10.255.255.1:81/computeRoutes"  # 不可达
    r = svc.get_routes("裕廊东", "滨海湾", "transit")
    assert r["status"] == "error"


def test_google_maps_http_error(monkeypatch):
    """HTTP 错误响应应返回明确错误。"""
    svc = GoogleMapsRoutesService(api_key="test-key")
    svc.endpoint = "https://httpbin.org/status/401"
    r = svc.get_routes("裕廊东", "滨海湾", "transit")
    assert r["status"] == "error"


def test_google_maps_traffic_empty():
    """Google Routes 不提供交通事件，返回明确空结果。"""
    svc = GoogleMapsRoutesService(api_key="")
    r = svc.get_traffic_incidents()
    assert r["status"] == "ok"
    assert r["data"]["incidents"] == []


def test_google_maps_fare_int_units():
    """transitFare.units 为整数（分）时应正确换算为新加坡元。"""
    svc = GoogleMapsRoutesService(api_key="")
    # units 190 -> S$1.90
    assert svc._fare_sgd({"transitFare": {"currencyCode": "SGD", "units": 190}}) == pytest.approx(1.9)
    # 带 nanos 小数部分
    assert svc._fare_sgd({"transitFare": {"currencyCode": "SGD", "units": 190, "nanos": 500000000}}) == pytest.approx(2.4)


def test_google_maps_fare_str_units():
    """transitFare.units 为字符串数字时也应正确换算。"""
    svc = GoogleMapsRoutesService(api_key="")
    assert svc._fare_sgd({"transitFare": {"currencyCode": "SGD", "units": "190"}}) == pytest.approx(1.9)


def test_google_maps_fare_missing():
    """无 transitFare 时应返回 None（不伪造费用）。"""
    svc = GoogleMapsRoutesService(api_key="")
    assert svc._fare_sgd({}) is None
    assert svc._fare_sgd({"transitFare": None}) is None


def test_google_maps_transfers_count():
    """换乘次数应按 TRANSIT 段数量减 1 计算。"""
    svc = GoogleMapsRoutesService(api_key="")
    # 2 个 TRANSIT 段 -> 1 次换乘
    route_two = {"legs": [{"steps": [
        {"travelMode": "WALK"},
        {"travelMode": "TRANSIT", "transitDetails": {"transitLine": {"name": "EWL"}}},
        {"travelMode": "TRANSIT", "transitDetails": {"transitLine": {"name": "NSL"}}},
        {"travelMode": "WALK"},
    ]}]}
    assert svc._transfers(route_two) == 1

    # 1 个 TRANSIT 段 -> 0 次换乘
    route_one = {"legs": [{"steps": [
        {"travelMode": "WALK"},
        {"travelMode": "TRANSIT", "transitDetails": {"transitLine": {"name": "EWL"}}},
        {"travelMode": "WALK"},
    ]}]}
    assert svc._transfers(route_one) == 0

    # 无 TRANSIT 段 -> 回退 legs-1
    route_no_transit = {"legs": [{"steps": [{"travelMode": "WALK"}]}]}
    assert svc._transfers(route_no_transit) == 0
