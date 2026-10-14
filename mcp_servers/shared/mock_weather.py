"""Mock Weather 服务：生成演示天气预报与天气风险。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.result import make_result
from shared.weather_service import WeatherService


class MockWeatherService(WeatherService):
    source_name = "mock"

    def get_weather_forecast(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        return make_result(
            "ok",
            {
                "location": location,
                "forecast_time": forecast_time,
                "condition": "阵雨",
                "temperature_c": 28.5,
                "humidity_pct": 82,
                "rain_probability_pct": 60,
                "rain_mm": 2.5,
                "wind_kmh": 12,
            },
            source=self.source_name,
        )

    def check_weather_risk(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        forecast = self.get_weather_forecast(location, forecast_time)
        rain_prob = forecast["data"]["rain_probability_pct"]
        if rain_prob >= 70:
            risk_level = "high"
            advice = "降雨概率高，建议携带雨具并预留额外通勤时间"
        elif rain_prob >= 40:
            risk_level = "medium"
            advice = "可能有阵雨，建议携带折叠伞"
        else:
            risk_level = "low"
            advice = "天气状况良好，通勤影响较小"
        return make_result(
            "ok",
            {
                "location": location,
                "forecast_time": forecast_time,
                "risk_level": risk_level,
                "rain_probability_pct": rain_prob,
                "advice": advice,
            },
            source=self.source_name,
        )
