"""Weather MCP Server：天气预报与通勤天气风险。

独立启动，暴露以下工具：
- get_weather_forecast
- check_weather_risk

数据源：
- 默认启用 Open-Meteo（免费、无需 Key）。
- 通过环境变量 WEATHER_PROVIDER 可切换：open_meteo（默认）| mock。
- 真实源调用失败时由工具层返回 status=error，不再自动降级到 Mock，
  以保证 source 语义诚实（不将失败伪装成模拟数据）。
"""
from __future__ import annotations

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env（从项目根目录）
try:
    from dotenv import load_dotenv

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except Exception:  # noqa: BLE001
    pass

from mcp.server.fastmcp import FastMCP  # noqa: E402
from shared.mock_weather import MockWeatherService  # noqa: E402
from shared.open_meteo_service import OpenMeteoWeatherService  # noqa: E402
from shared.weather_service import WeatherService  # noqa: E402

mcp = FastMCP("weather")


def _build_service() -> WeatherService:
    """根据环境变量选择天气数据源。

    WEATHER_PROVIDER=mock 时使用 Mock；否则默认使用 Open-Meteo（真实、免费）。
    """
    provider = os.getenv("WEATHER_PROVIDER", "open_meteo").strip().lower()
    if provider == "mock":
        return MockWeatherService()
    return OpenMeteoWeatherService()


_service = _build_service()


@mcp.tool()
def get_weather_forecast(
    location: str, forecast_time: Optional[str] = None
) -> dict:
    """查询指定地点和时间的天气预报。

    Args:
        location: 地点名称。
        forecast_time: 可选，预报时间，ISO 8601 字符串。
    """
    return _service.get_weather_forecast(location, forecast_time)


@mcp.tool()
def check_weather_risk(
    location: str, forecast_time: Optional[str] = None
) -> dict:
    """分析降雨等天气对通勤的潜在影响。

    Args:
        location: 地点名称。
        forecast_time: 可选，预报时间，ISO 8601 字符串。
    """
    return _service.check_weather_risk(location, forecast_time)


if __name__ == "__main__":
    mcp.run()
