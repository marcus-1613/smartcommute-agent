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
    """HTTP 错误响应应返回明确错误，不伪造数据。"""
    svc = OpenMeteoWeatherService(endpoint="https://httpbin.org/status/500")
    r = svc.get_weather_forecast("裕廊东")
    assert r["status"] == "error"
    assert r["source"] == "open_meteo"


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
    assert LTATrafficService._map_severity("Other") == "low"
    assert LTATrafficService._map_severity(None) == "low"


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
