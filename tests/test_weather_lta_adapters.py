"""天气与交通事件适配器测试：Open-Meteo、LTA、Mock 路径、source 语义。"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_servers"))

from shared.open_meteo_service import OpenMeteoWeatherService
from shared.lta_service import LTATrafficService
from shared.mock_weather import MockWeatherService
from shared.mock_mobility import MockMobilityService


# ---------- Open-Meteo ----------

def test_open_meteo_source_name():
    svc = OpenMeteoWeatherService()
    assert svc.source_name == "open_meteo"


def test_open_meteo_resolve_coordinates_known():
    svc = OpenMeteoWeatherService()
    assert svc._resolve_coordinates("裕廊东") == (1.3331, 103.7421)
    assert svc._resolve_coordinates("Jurong East") is not None


def test_open_meteo_resolve_coordinates_unknown():
    svc = OpenMeteoWeatherService()
    assert svc._resolve_coordinates("不存在的某地XYZ") is None


def test_open_meteo_unknown_location_returns_error():
    svc = OpenMeteoWeatherService()
    r = svc.get_weather_forecast("不存在的某地XYZ")
    assert r["status"] == "error"
    assert r["source"] == "open_meteo"
    assert "无法解析" in r["error"]


def test_open_meteo_condition_mapping():
    assert OpenMeteoWeatherService._condition_from_code(0) == "晴"
    assert OpenMeteoWeatherService._condition_from_code(80) == "阵雨"
    assert OpenMeteoWeatherService._condition_from_code(None) == "未知"
    assert OpenMeteoWeatherService._condition_from_code(999) == "未知"


def test_open_meteo_select_hour_index():
    times = ["2026-10-14T08:00", "2026-10-14T09:00", "2026-10-14T10:00"]
    assert OpenMeteoWeatherService._select_hour_index(times, "09:00") == 1
    assert OpenMeteoWeatherService._select_hour_index(times, None) == 0
    assert OpenMeteoWeatherService._select_hour_index(times, "23:00") == 0  # 未命中回退


def test_open_meteo_http_error(monkeypatch):
    """HTTP 错误响应应返回明确错误，不伪造数据（不依赖外网，用 monkeypatch 模拟）。"""
    import httpx

    svc = OpenMeteoWeatherService(endpoint="https://example.invalid/forecast")

    class _FakeResp:
        status_code = 500

        def json(self):
            return {}

    def _fake_get(*args, **kwargs):
        return _FakeResp()

    monkeypatch.setattr(httpx, "get", _fake_get)
    r = svc.get_weather_forecast("裕廊东")
    assert r["status"] == "error"
    assert r["source"] == "open_meteo"
    assert "500" in r["error"]


# ---------- LTA 交通事件 ----------

def test_lta_source_name():
    svc = LTATrafficService(account_key="")
    assert svc.source_name == "lta_datamall"


def test_lta_missing_key_returns_error():
    svc = LTATrafficService(account_key="")
    r = svc.get_traffic_incidents()
    assert r["status"] == "error"
    assert "LTA_ACCOUNT_KEY" in r["error"]
    assert r["source"] == "lta_datamall"


def test_lta_convert_incidents():
    svc = LTATrafficService(account_key="")
    payload = {
        "value": [
            {"IncidentID": "1", "Type": "Accident", "Message": "事故", "RoadName": "PIE"},
            {"IncidentID": "2", "Type": "Road Works", "Message": "施工", "RoadName": "CTE"},
        ]
    }
    incidents = svc._convert_incidents(payload, None)
    assert len(incidents) == 2
    assert incidents[0]["id"] == "1"
    assert incidents[0]["type"] == "Accident"
    assert incidents[0]["severity"] == "high"
    assert incidents[1]["severity"] == "medium"


def test_lta_convert_incidents_area_filter():
    svc = LTATrafficService(account_key="")
    payload = {"value": [{"IncidentID": "1", "Type": "Accident", "Message": "x", "RoadName": "PIE"}]}
    assert len(svc._convert_incidents(payload, "PIE")) == 1
    assert len(svc._convert_incidents(payload, "CTE")) == 0


def test_lta_severity_mapping():
    assert LTATrafficService._map_severity("Accident") == "high"
    assert LTATrafficService._map_severity("Road Works") == "medium"
    assert LTATrafficService._map_severity("Roadwork") == "medium"  # 真实字段是一个词
    assert LTATrafficService._map_severity("Vehicle Breakdown") == "medium"
    assert LTATrafficService._map_severity("Heavy Traffic") == "low"
    assert LTATrafficService._map_severity("Other") == "low"
    assert LTATrafficService._map_severity(None) == "low"


def test_lta_convert_real_field_structure():
    """按 LTA 真实响应字段（Type/Message/Latitude/Longitude，无 IncidentID/RoadName）转换。"""
    svc = LTATrafficService(account_key="")
    payload = {
        "value": [
            {
                "Type": "Accident",
                "Latitude": 1.32,
                "Longitude": 103.86,
                "Message": "(14/10)13:46 Accident on PIE (towards Changi) after CTE",
            },
            {
                "Type": "Roadwork",
                "Latitude": 1.33,
                "Longitude": 103.77,
                "Message": "(14/10)14:18 Road Works on Bukit Timah Road (towards City)",
            },
        ]
    }
    incidents = svc._convert_incidents(payload, None)
    assert len(incidents) == 2

    a = incidents[0]
    assert a["id"] == "lta-0"  # 无 IncidentID 时用索引生成
    assert a["type"] == "Accident"
    assert a["severity"] == "high"
    assert a["area"] == "PIE"  # 从 Message 提取
    assert a["latitude"] == 1.32
    assert a["longitude"] == 103.86

    b = incidents[1]
    assert b["id"] == "lta-1"
    assert b["severity"] == "medium"  # Roadwork 单词语义
    assert b["area"] == "Bukit Timah Road"  # 完整道路名，非 "Buki"


def test_lta_extract_area_from_message():
    """从 Message 提取道路名，覆盖缩写与完整道路名。"""
    assert LTATrafficService._extract_area({"Message": "Heavy Traffic on CTE (towards AYE)"}) == "CTE"
    assert LTATrafficService._extract_area({"Message": "Road Works on Bukit Timah Road (towards City)"}) == "Bukit Timah Road"
    assert LTATrafficService._extract_area({"RoadName": "PIE"}) == "PIE"  # 优先 RoadName
    assert LTATrafficService._extract_area({}) == ""


def test_lta_convert_incidents_area_filter_from_message():
    """区域过滤应基于从 Message 提取的道路名。"""
    svc = LTATrafficService(account_key="")
    payload = {"value": [
        {"Type": "Accident", "Message": "Accident on PIE (towards Changi)"},
        {"Type": "Roadwork", "Message": "Road Works on CTE (towards AYE)"},
    ]}
    assert len(svc._convert_incidents(payload, "PIE")) == 1
    assert len(svc._convert_incidents(payload, "CTE")) == 1
    assert len(svc._convert_incidents(payload, "BKE")) == 0


def test_lta_timeout():
    """请求超时应返回明确错误，不抛异常，source 仍为 lta_datamall。"""
    svc = LTATrafficService(account_key="test-key", timeout=0.001)
    svc.endpoint = "http://10.255.255.1:81/TrafficIncidents"  # 不可达，模拟超时
    r = svc.get_traffic_incidents()
    assert r["status"] == "error"
    assert r["source"] == "lta_datamall"


def test_lta_http_error(monkeypatch):
    """HTTP 非 200 响应应返回明确错误，不伪造数据（不依赖外网）。"""
    import httpx

    svc = LTATrafficService(account_key="test-key")
    svc.endpoint = "https://example.invalid/TrafficIncidents"

    class _FakeResp:
        status_code = 401

        def json(self):
            return {}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp())
    r = svc.get_traffic_incidents()
    assert r["status"] == "error"
    assert r["source"] == "lta_datamall"
    assert "401" in r["error"]


def test_lta_malformed_response():
    """畸形/非预期结构响应应容错，不崩溃。"""
    svc = LTATrafficService(account_key="test-key")
    # value 为 None 时应返回空列表（容错）
    assert svc._convert_incidents({"value": None}, None) == []
    # payload 非 dict 也应容错
    assert svc._convert_incidents(None, None) == []


def test_lta_convert_incidents_non_dict_items():
    """value 中含非 dict 元素时应跳过，不崩溃。"""
    svc = LTATrafficService(account_key="")
    payload = {"value": ["not-a-dict", {"IncidentID": "1", "Type": "Accident", "Message": "x", "RoadName": "PIE"}]}
    incidents = svc._convert_incidents(payload, None)
    assert len(incidents) == 1
    assert incidents[0]["id"] == "1"


# ---------- Mock 路径（无 Key 时 source 仍为 mock） ----------

def test_mock_weather_source():
    svc = MockWeatherService()
    assert svc.get_weather_forecast("滨海湾")["source"] == "mock"


def test_mock_mobility_traffic_source():
    svc = MockMobilityService()
    r = svc.get_traffic_incidents()
    assert r["status"] == "ok"
    assert r["source"] == "mock"
    assert len(r["data"]["incidents"]) >= 1
