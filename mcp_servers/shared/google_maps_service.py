"""Google Maps Routes API 适配器。

实现 MobilityService 接口，调用 Google Maps Platform 的 Routes API。
将外部响应转换为项目统一的路线数据模型。

注意：
- API Key 仅从环境变量读取，不写入日志。
- 设置超时、错误处理与日志脱敏。
- 返回统一结构（status/data/source/queried_at/error）。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from shared.result import make_result
from shared.mobility_service import MobilityService

logger = logging.getLogger(__name__)


class GoogleMapsRoutesService(MobilityService):
    """基于 Google Maps Routes API 的真实路线服务。"""

    source_name = "google_maps"

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY", "")
        self.endpoint = endpoint or os.getenv(
            "GOOGLE_MAPS_ROUTES_ENDPOINT",
            "https://routes.googleapis.com/directions/v2:computeRoutes",
        )
        self.timeout = timeout

    # ---------- 工具实现 ----------

    def search_place(self, query: str) -> Dict[str, Any]:
        """Google Routes API 不提供独立的 place 搜索；
        这里通过一次最小化路线请求解析地点，或用 Place 文本搜索。
        简化实现：返回原始地名作为标准化结果，交由路线请求校验。
        """
        # 暂不单独调用 Place API，返回地名本身（真实校验发生在 get_routes）
        return make_result(
            "ok",
            {"name": query, "type": "place", "coordinates": None},
            source=self.source_name,
        )

    def get_routes(
        self,
        origin: str,
        destination: str,
        mode: str = "transit",
        departure_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error="未配置 GOOGLE_MAPS_API_KEY",
            )

        travel_mode = "TRANSIT" if mode == "transit" else "DRIVE"
        body: Dict[str, Any] = {
            "origin": {"address": origin},
            "destination": {"address": destination},
            "travelMode": travel_mode,
            "computeAlternativeRoutes": True,
            "languageCode": "zh-CN",
            "units": "METRIC",
        }
        if departure_time:
            body["departureTime"] = departure_time

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "routes.duration,routes.distanceMeters,"
                "routes.transitFare,routes.legs,routes.description,"
                "routes.polyline.encodedPolyline"
            ),
        }

        try:
            resp = httpx.post(
                self.endpoint,
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            logger.error("Google Maps 请求超时")
            return make_result(
                "error", data=None, source=self.source_name,
                error="请求超时",
            )
        except httpx.HTTPError as exc:
            # 脱敏：不记录 URL 中的 key
            logger.error("Google Maps 请求失败：%s", type(exc).__name__)
            return make_result(
                "error", data=None, source=self.source_name,
                error=f"网络错误：{type(exc).__name__}",
            )

        if resp.status_code != 200:
            logger.error(
                "Google Maps 返回 %s（脱敏：不含 key）", resp.status_code
            )
            return make_result(
                "error", data=None, source=self.source_name,
                error=f"API 返回 {resp.status_code}",
            )

        try:
            payload = resp.json()
            routes = self._convert_routes(payload, mode)
            return make_result(
                "ok",
                {
                    "origin": origin,
                    "destination": destination,
                    "mode": mode,
                    "departure_time": departure_time,
                    "routes": routes,
                },
                source=self.source_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Google Maps 响应解析失败")
            return make_result(
                "error", data=None, source=self.source_name,
                error=f"响应解析失败：{exc}",
            )

    def get_traffic_incidents(self, area: Optional[str] = None) -> Dict[str, Any]:
        """Routes API 不提供交通事件接口，返回空结果（明确标记）。"""
        return make_result(
            "ok",
            {"incidents": [], "note": "Google Routes API 不提供交通事件，此数据源为空"},
            source=self.source_name,
        )

    # ---------- 数据转换 ----------

    def _convert_routes(self, payload: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
        """将 Google Routes API 响应转换为统一路线模型。"""
        routes: List[Dict[str, Any]] = []
        for i, r in enumerate(payload.get("routes", [])):
            route = {
                "id": f"gm-{i}",
                "summary": r.get("description", f"路线 {i + 1}"),
                "mode": "transit" if mode == "transit" else "driving",
                "duration_min": self._duration_minutes(r),
                "fare_sgd": self._fare_sgd(r),
                "walk_distance_m": self._walk_distance(r),
                "transfers": self._transfers(r),
                "steps": self._convert_steps(r),
            }
            routes.append(route)
        return routes

    def _duration_minutes(self, route: Dict[str, Any]) -> Optional[float]:
        duration = route.get("duration")
        if isinstance(duration, str):
            # 解析 "1234s" 格式
            return self._parse_duration_seconds(duration) / 60
        return None

    def _fare_sgd(self, route: Dict[str, Any]) -> Optional[float]:
        fare = route.get("transitFare")
        if isinstance(fare, dict):
            # Google 返回的是最小货币单位（分）：
            # units 为整数货币值（如 190 表示 S$1.90），nanos 为纳元小数部分（1e-9）。
            units = fare.get("units")
            nanos = fare.get("nanos", 0)
            if isinstance(units, int):
                return float(units) / 100 + float(nanos) / 1e9
            if isinstance(units, str):
                # 兼容字符串数字形式（如 "190"）
                stripped = units.strip()
                if stripped.isdigit():
                    return int(stripped) / 100 + float(nanos) / 1e9
        return None

    def _walk_distance(self, route: Dict[str, Any]) -> Optional[float]:
        total = 0
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                if step.get("travelMode") == "WALK":
                    # 简化：用 step 的 distanceMeters
                    total += step.get("distanceMeters", 0)
        return total if total > 0 else None

    def _transfers(self, route: Dict[str, Any]) -> Optional[int]:
        """估算换乘次数。

        Google Routes API 中一次完整行程可含多个 leg（步行→乘车→步行→换乘→乘车…）。
        粗略估算：统计所有 leg 中出现的 TRANSIT 段数量，换乘次数 = 乘车段数 - 1。
        若无法确定，则回退为 legs 数量 - 1。
        """
        transit_steps = 0
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                if step.get("travelMode") == "TRANSIT":
                    transit_steps += 1
        if transit_steps > 0:
            return transit_steps - 1
        legs = route.get("legs", [])
        return max(0, len(legs) - 1) if legs else None

    def _convert_steps(self, route: Dict[str, Any]) -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = []
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                mode = step.get("travelMode", "")
                step_type = self._map_travel_mode(mode)
                transit = step.get("transitDetails", {})
                steps.append(
                    {
                        "type": step_type,
                        "description": self._step_description(step, mode),
                        "line": self._transit_line(transit),
                        "distance_m": step.get("distanceMeters"),
                        "duration_min": (
                            self._parse_duration_seconds(step.get("duration")) / 60
                            if isinstance(step.get("duration"), str)
                            else None
                        ),
                    }
                )
        return steps

    def _map_travel_mode(self, mode: str) -> str:
        return {
            "WALK": "walk",
            "TRANSIT": "transit",
            "DRIVE": "drive",
        }.get(mode, mode.lower())

    def _step_description(self, step: Dict[str, Any], mode: str) -> str:
        transit = step.get("transitDetails", {})
        if mode == "TRANSIT":
            line_name = self._transit_line(transit)
            if line_name:
                return f"乘坐 {line_name}"
            return "乘坐公共交通"
        if mode == "WALK":
            return "步行"
        if mode == "DRIVE":
            return "驾车"
        return step.get("description", mode)

    def _transit_line(self, transit: Dict[str, Any]) -> Optional[str]:
        if not transit:
            return None
        line = transit.get("transitLine", {})
        name = line.get("name")
        short = line.get("nameShort")
        return short or name

    @staticmethod
    def _parse_duration_seconds(duration: str) -> float:
        """解析 '1234s' 格式的时长为秒。"""
        if duration.endswith("s"):
            try:
                return float(duration[:-1])
            except ValueError:
                return 0.0
        return 0.0
