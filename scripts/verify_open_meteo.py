"""Open-Meteo 真实 API 验证脚本（可复现验证证据）。

用途：在本地环境直接验证 Open-Meteo 免费天气 API 的真实调用，
确认适配器能正确解析响应并标记 source="open_meteo"。

注意：
- 此脚本会发起真实外网请求，独立于 pytest（pytest 默认走 Mock，不依赖外网）。
- 运行：python scripts/verify_open_meteo.py
- 输出：真实天气数据 + source 标记，用于人工核对。
"""
from __future__ import annotations

import os
import sys

# 将 mcp_servers 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_servers"))

from shared.open_meteo_service import OpenMeteoWeatherService  # noqa: E402


def main() -> None:
    svc = OpenMeteoWeatherService()
    print(f"数据源: {svc.source_name}")
    print(f"端点: {svc.endpoint}")
    print("-" * 50)

    # 1) 天气预报
    forecast = svc.get_weather_forecast("裕廊东")
    print("【天气预报】")
    print(f"  status: {forecast['status']}")
    print(f"  source: {forecast['source']}")
    if forecast["status"] == "ok":
        d = forecast["data"]
        print(f"  地点: {d['location']}  坐标: {d['coordinates']}")
        print(f"  时间: {d['forecast_time']}")
        print(f"  天气: {d['condition']}  温度: {d['temperature_c']}°C")
        print(f"  湿度: {d['humidity_pct']}%  降雨概率: {d['rain_probability_pct']}%")
        print(f"  降雨量: {d['rain_mm']}mm  风速: {d['wind_kmh']}km/h")
    else:
        print(f"  错误: {forecast['error']}")

    print("-" * 50)

    # 2) 天气风险
    risk = svc.check_weather_risk("裕廊东")
    print("【天气风险】")
    print(f"  status: {risk['status']}  source: {risk['source']}")
    if risk["status"] == "ok":
        print(f"  风险等级: {risk['data']['risk_level']}")
        print(f"  建议: {risk['data']['advice']}")
    else:
        print(f"  错误: {risk['error']}")


if __name__ == "__main__":
    main()
