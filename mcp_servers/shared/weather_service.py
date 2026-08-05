"""Weather 数据源服务：天气预报与通勤天气风险。"""
from __future__ import annotations

from typing import Any, Dict, Optional


class WeatherService:
    def get_weather_forecast(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def check_weather_risk(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        raise NotImplementedError
