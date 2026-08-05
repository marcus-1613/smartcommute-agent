"""Open-Meteo 天气适配器。

实现 WeatherService 接口，调用 Open-Meteo 免费天气 API（无需 Key）。
将外部响应转换为项目统一的天气预报 / 天气风险结构。

Open-Meteo：
- 免费、无需 API Key
- 支持经纬度查询当前与未来天气
- 返回温度、湿度、降雨概率、降雨量、风速等

注意：
- 坐标优先从 PLACES 静态库映射；无法映射时报错（不伪造坐标）。
- 设置超时与错误处理，失败返回 status=error（由上层决定是否降级）。
- 返回统一结构（status/data/source/queried_at/error），source 固定为 "open_meteo"。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from shared.result import make_result
from shared.singapore_data import PLACES
from shared.weather_service import WeatherService

logger = logging.getLogger(__name__)

# Open-Meteo 当前天气 + 逐小时预报端点
_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# 请求的天气字段
_WEATHER_FIELDS = (
    "temperature_2m,relative_humidity_2m,precipitation_probability,"
    "precipitation,wind_speed_10m,weather_code"
)


class OpenMeteoWeatherService(WeatherService):
    """基于 Open-Meteo 免费 API 的真实天气服务（无需 Key）。"""

    source_name = "open_meteo"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.endpoint = endpoint or _OPEN_METEO_URL
        self.timeout = timeout

    # ---------- 工具实现 ----------

    def get_weather_forecast(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        coord = self._resolve_coordinates(location)
        if coord is None:
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"无法解析地点坐标：{location}（仅支持新加坡已知地点）",
            )

        lat, lng = coord
        # 逐小时预报，未来 24 小时；forecast_time 精确到小时则只取对应时段
        params: Dict[str, Any] = {
            "latitude": lat,
            "longitude": lng,
            "hourly": _WEATHER_FIELDS,
            "forecast_days": 1,
            "timezone": "Asia/Singapore",
        }
        try:
            resp = httpx.get(self.endpoint, params=params, timeout=self.timeout)
        except httpx.TimeoutException:
            logger.error("Open-Meteo 请求超时")
            return make_result(
                "error", data=None, source=self.source_name, error="请求超时"
            )
        except httpx.HTTPError as exc:
            logger.error("Open-Meteo 请求失败：%s", type(exc).__name__)
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"网络错误：{type(exc).__name__}",
            )

        if resp.status_code != 200:
            logger.error("Open-Meteo 返回 %s", resp.status_code)
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"API 返回 {resp.status_code}",
            )

        try:
            payload = resp.json()
            hourly = payload.get("hourly", {})
            times = hourly.get("time", [])
            if not times:
                raise ValueError("响应缺少 hourly.time")

            idx = self._select_hour_index(times, forecast_time)
            data = {
                "location": location,
                "forecast_time": times[idx],
                "condition": self._condition_from_code(
                    hourly.get("weather_code", [None] * len(times))[idx]
                ),
                "temperature_c": hourly.get("temperature_2m", [None] * len(times))[idx],
                "humidity_pct": hourly.get("relative_humidity_2m", [None] * len(times))[idx],
                "rain_probability_pct": hourly.get(
                    "precipitation_probability", [None] * len(times)
                )[idx],
                "rain_mm": hourly.get("precipitation", [None] * len(times))[idx],
                "wind_kmh": hourly.get("wind_speed_10m", [None] * len(times))[idx],
                "coordinates": [lat, lng],
            }
            return make_result("ok", data, source=self.source_name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Open-Meteo 响应解析失败")
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"响应解析失败：{exc}",
            )

    def check_weather_risk(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        forecast = self.get_weather_forecast(location, forecast_time)
        if forecast["status"] != "ok":
            return make_result(
                forecast["status"],
                data=None,
                source=self.source_name,
                error=forecast.get("error", "天气查询失败"),
            )

        data = forecast["data"]
        rain_prob = data.get("rain_probability_pct")
        if rain_prob is None:
            rain_prob = 0
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
                "forecast_time": data.get("forecast_time"),
                "risk_level": risk_level,
                "rain_probability_pct": rain_prob,
                "advice": advice,
            },
            source=self.source_name,
        )

    # ---------- 内部工具 ----------

    def _resolve_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
        """从静态地点库解析经纬度（不做地理编码，避免伪造）。"""
        q = location.strip().lower()
        if q in PLACES:
            coord = PLACES[q][2]
            return (coord[0], coord[1])
        # 模糊匹配
        for key, (_, _, coord) in PLACES.items():
            if key in q or q in key:
                return (coord[0], coord[1])
        return None

    @staticmethod
    def _select_hour_index(times: List[str], forecast_time: Optional[str]) -> int:
        """选择预报时间对应的小时索引，缺省取最近未来时段。

        times 为 ISO 8601 本地时间（如 "2026-10-14T08:00"）。
        forecast_time 可为 "08:00" 或完整 ISO 时间。
        """
        if not forecast_time:
            return 0
        # 提取 HH:MM
        hhmm = forecast_time
        if "T" in hhmm:
            hhmm = hhmm.split("T")[1]
        if ":" in hhmm:
            hhmm = hhmm[:5]
        for i, t in enumerate(times):
            if t.endswith(hhmm) or t.split("T")[1].startswith(hhmm):
                return i
        return 0

    @staticmethod
    def _condition_from_code(code: Optional[int]) -> str:
        """将 WMO 天气代码映射为中文天气描述。"""
        mapping = {
            0: "晴",
            1: "多云",
            2: "阴",
            3: "阴",
            45: "雾",
            48: "雾凇",
            51: "毛毛雨",
            53: "毛毛雨",
            55: "毛毛雨",
            61: "小雨",
            63: "中雨",
            65: "大雨",
            71: "小雪",
            73: "中雪",
            75: "大雪",
            80: "阵雨",
            81: "阵雨",
            82: "强阵雨",
            95: "雷阵雨",
            96: "雷阵雨伴冰雹",
            99: "雷阵雨伴冰雹",
        }
        if code is None:
            return "未知"
        return mapping.get(code, "未知")
