"""OneMap Routing API 适配器。

实现 MobilityService 接口，调用新加坡 OneMap 官方 Routing API
（https://www.onemap.gov.sg/api/public/routingsvc/route），提供真实的
驾车 / 公交 / 步行 / 骑行路线。

关键说明：
- 认证：通过 HTTP 头 ``Authorization: <token>`` 传递，Token 仅从环境变量读取。
- 坐标：OneMap 要求 WGS84 经纬度（"lat,lng"），本适配器不接收地址字符串作坐标，
  而是通过 ``search_place`` 将地名解析为坐标（复用 PLACES 库）。
- 响应结构：drive/walk/cycle 返回 ``route_summary``（total_time 秒 /
  total_distance 米）、``route_instructions``（嵌套数组）、``route_geometry``
  （encoded polyline）；pt（公交）返回 ``plan.itineraries[]``。
  两者分别解析，统一转换为项目路线模型。
- 超时、错误处理与日志脱敏，失败绝不伪造真实路线数据。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from shared.result import make_result
from shared.mobility_service import MobilityService
from shared.singapore_data import PLACES

logger = logging.getLogger(__name__)

# OneMap Routing API 端点（官方）
_ONEMAP_ROUTING_ENDPOINT = (
    "https://www.onemap.gov.sg/api/public/routingsvc/route"
)

# 项目 mode -> OneMap routeType 映射
_MODE_TO_ROUTE_TYPE = {
    "transit": "pt",
    "driving": "drive",
    "walk": "walk",
    "walking": "walk",
    "cycling": "cycle",
    "cycle": "cycle",
    "all": "pt",  # "all" 默认按公交处理
}

# pt 模式下的公交子模式
_PT_MODE = "TRANSIT"


class OneMapRoutesService(MobilityService):
    """基于 OneMap Routing API 的真实路线服务。"""

    source_name = "onemap"

    def __init__(
        self,
        token: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.token = token or os.getenv("ONEMAP_TOKEN", "")
        self.endpoint = endpoint or os.getenv(
            "ONEMAP_ROUTING_ENDPOINT", _ONEMAP_ROUTING_ENDPOINT
        )
        self.timeout = timeout

    # ---------- 工具实现 ----------

    def search_place(self, query: str) -> Dict[str, Any]:
        """将地名解析为 WGS84 坐标。

        OneMap 有独立的 search API，但为避免额外依赖，这里复用项目内
        PLACES 静态坐标库（与 Mock 一致）。无法解析时返回明确错误，
        不把地址字符串当作坐标传入路线 API。
        """
        q = query.strip().lower()
        if q in PLACES:
            name, typ, coord = PLACES[q]
            return make_result(
                "ok",
                {"name": name, "type": typ, "coordinates": coord},
                source=self.source_name,
            )
        # 模糊匹配
        for key, (name, typ, coord) in PLACES.items():
            if key in q or q in key:
                return make_result(
                    "ok",
                    {"name": name, "type": typ, "coordinates": coord},
                    source=self.source_name,
                )
        return make_result(
            "error",
            data=None,
            source=self.source_name,
            error=f"无法解析地点坐标为 WGS84：{query}",
        )

    def _resolve_coordinates(self, place: str) -> Optional[List[float]]:
        """解析地名为 [lat, lng]；失败返回 None。"""
        r = self.search_place(place)
        if r["status"] != "ok":
            return None
        coord = r["data"].get("coordinates")
        if not isinstance(coord, (list, tuple)) or len(coord) != 2:
            return None
        return [float(coord[0]), float(coord[1])]

    def get_routes(
        self,
        origin: str,
        destination: str,
        mode: str = "transit",
        departure_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询出发地到目的地的真实路线。"""
        if not self.token:
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error="未配置 ONEMAP_TOKEN",
            )

        # 坐标解析（不允许把地址字符串当坐标传入）
        start = self._resolve_coordinates(origin)
        end = self._resolve_coordinates(destination)
        if start is None or end is None:
            missing = origin if start is None else destination
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"无法解析地点坐标为 WGS84：{missing}",
            )

        route_type = _MODE_TO_ROUTE_TYPE.get(mode, "pt")

        # OneMap 参数：date/time 必填
        date_str, time_str = self._build_datetime(departure_time)

        params: Dict[str, str] = {
            "start": f"{start[0]},{start[1]}",
            "end": f"{end[0]},{end[1]}",
            "routeType": route_type,
            "date": date_str,
            "time": time_str,
        }
        if route_type == "pt":
            params["mode"] = _PT_MODE
            params["numItineraries"] = "3"

        headers = {"Authorization": self.token}

        try:
            resp = httpx.get(
                self.endpoint,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.TimeoutException:
            logger.error("OneMap 路线请求超时")
            return make_result(
                "error", data=None, source=self.source_name, error="请求超时"
            )
        except httpx.HTTPError as exc:
            logger.error("OneMap 路线请求失败：%s", type(exc).__name__)
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"网络错误：{type(exc).__name__}",
            )

        if resp.status_code != 200:
            # 404 表示无可用路线，401/403 表示认证失败
            logger.error("OneMap 路线返回 %s", resp.status_code)
            if resp.status_code == 404:
                return make_result(
                    "error",
                    data=None,
                    source=self.source_name,
                    error="无可用路线（两点间未找到可行路径）",
                )
            if resp.status_code in (401, 403):
                return make_result(
                    "error",
                    data=None,
                    source=self.source_name,
                    error="OneMap Token 认证失败（401/403）",
                )
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"API 返回 {resp.status_code}",
            )

        try:
            payload = resp.json()
            routes = self._convert_routes(payload, route_type, mode)
            if not routes:
                return make_result(
                    "error",
                    data=None,
                    source=self.source_name,
                    error="无可用路线（响应无有效路线数据）",
                )
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
            logger.exception("OneMap 路线响应解析失败")
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"响应解析失败：{exc}",
            )

    def get_traffic_incidents(self, area: Optional[str] = None) -> Dict[str, Any]:
        """OneMap Routing 不提供交通事件接口，返回空结果（明确标记）。"""
        return make_result(
            "ok",
            {"incidents": [], "note": "OneMap Routing 不提供交通事件，此数据源为空"},
            source=self.source_name,
        )

    # ---------- 数据转换 ----------

    def _convert_routes(
        self, payload: Dict[str, Any], route_type: str, mode: str
    ) -> List[Dict[str, Any]]:
        """将 OneMap 响应转换为统一路线模型。

        pt（公交）与 drive/walk/cycle 响应结构不同，分别处理。
        """
        if route_type == "pt":
            return self._convert_pt_routes(payload, mode)
        return self._convert_drive_walk_routes(payload, route_type, mode)

    def _convert_drive_walk_routes(
        self, payload: Dict[str, Any], route_type: str, mode: str
    ) -> List[Dict[str, Any]]:
        """解析 drive/walk/cycle 响应（route_summary + route_instructions）。"""
        summary = payload.get("route_summary") or {}
        total_time_s = summary.get("total_time")  # 秒
        total_distance_m = summary.get("total_distance")  # 米

        # 关键字段缺失（畸形/无效响应）时不生成空路线
        if total_time_s is None and total_distance_m is None:
            return []

        instructions = payload.get("route_instructions") or []
        steps = self._convert_instructions(instructions)

        route_mode = {
            "drive": "driving",
            "walk": "walking",
            "cycle": "cycling",
        }.get(route_type, mode)

        route = {
            "id": "onemap-0",
            "summary": self._summary_for_mode(route_mode),
            "mode": route_mode,
            "duration_min": self._seconds_to_minutes(total_time_s),
            "distance_m": self._to_float(total_distance_m),
            "fare_sgd": None,  # 驾车/步行/骑行 OneMap 不返回车费
            "walk_distance_m": self._walk_distance_from_steps(steps),
            "transfers": 0,
            "steps": steps,
            # 原始几何（encoded polyline），供后续空间分析，不虚构
            "route_geometry": payload.get("route_geometry"),
        }
        return [route]

    def _convert_pt_routes(
        self, payload: Dict[str, Any], mode: str
    ) -> List[Dict[str, Any]]:
        """解析 pt（公交）响应（plan.itineraries[]）。"""
        plan = payload.get("plan") or {}
        itineraries = plan.get("itineraries") or []
        routes: List[Dict[str, Any]] = []

        for i, itin in enumerate(itineraries):
            if not isinstance(itin, dict):
                continue
            duration_s = itin.get("duration")  # 秒
            walk_distance_m = itin.get("walkDistance")
            transfers = itin.get("transfers")
            fare = self._fare_sgd(itin.get("fare"))
            legs = itin.get("legs") or []
            steps = self._convert_legs(legs)

            routes.append(
                {
                    "id": f"onemap-{i}",
                    "summary": self._pt_summary(legs),
                    "mode": "transit",
                    "duration_min": self._seconds_to_minutes(duration_s),
                    "distance_m": self._total_leg_distance(legs),
                    "fare_sgd": fare,
                    "walk_distance_m": self._to_float(walk_distance_m),
                    "transfers": self._to_int(transfers),
                    "steps": steps,
                    "route_geometry": None,
                }
            )
        return routes

    def _convert_instructions(self, instructions: Any) -> List[Dict[str, Any]]:
        """解析 route_instructions（drive/walk/cycle 的嵌套数组）。

        每条指令是数组，按位置：[0]title, [1]road_name, [2]distance(米),
        [3]坐标, [4]time(秒), ... [9]instruction 文本。
        """
        steps: List[Dict[str, Any]] = []
        if not isinstance(instructions, list):
            return steps
        for instr in instructions:
            if not isinstance(instr, list):
                continue
            title = instr[0] if len(instr) > 0 else None
            road_name = instr[1] if len(instr) > 1 else None
            distance = instr[2] if len(instr) > 2 else None
            time_s = instr[4] if len(instr) > 4 else None
            text = instr[9] if len(instr) > 9 else None

            steps.append(
                {
                    "type": self._infer_step_type(title, road_name),
                    "description": text or title or "行驶",
                    "road_name": road_name,
                    "distance_m": self._to_float(distance),
                    "duration_min": self._seconds_to_minutes(time_s),
                }
            )
        return steps

    def _convert_legs(self, legs: Any) -> List[Dict[str, Any]]:
        """解析 pt 响应的 legs[]，转为统一 steps 模型。"""
        steps: List[Dict[str, Any]] = []
        if not isinstance(legs, list):
            return steps
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            leg_mode = (leg.get("mode") or "").upper()
            route_name = leg.get("route") or ""
            distance = leg.get("distance")
            duration_s = (
                (leg.get("endTime") - leg.get("startTime")) / 1000
                if isinstance(leg.get("endTime"), (int, float))
                and isinstance(leg.get("startTime"), (int, float))
                else None
            )
            from_name = (leg.get("from") or {}).get("name")
            to_name = (leg.get("to") or {}).get("name")

            if leg_mode == "WALK":
                desc = "步行"
                step_type = "walk"
            elif leg_mode in ("BUS", "SUBWAY", "RAIL", "TRAM"):
                desc = f"乘坐 {route_name or leg_mode}"
                step_type = "transit"
            else:
                desc = leg_mode or "行进"
                step_type = "transit" if route_name else "walk"

            if to_name:
                desc = f"{desc} → {to_name}"

            steps.append(
                {
                    "type": step_type,
                    "description": desc,
                    "line": route_name or None,
                    "distance_m": self._to_float(distance),
                    "duration_min": self._seconds_to_minutes(duration_s),
                }
            )
        return steps

    # ---------- 辅助 ----------

    @staticmethod
    def _build_datetime(departure_time: Optional[str]) -> tuple[str, str]:
        """生成 OneMap 需要的 date(MM-DD-YYYY) 与 time(HH:MM:SS)。

        departure_time 可能是 "HH:MM" 或 ISO 8601。若无法解析，用当前时间。
        """
        now = datetime.now()
        date_str = now.strftime("%m-%d-%Y")
        time_str = now.strftime("%H:%M:%S")

        if not departure_time:
            return date_str, time_str

        # 尝试解析 ISO 8601 中的日期/时间
        dt = _parse_iso(departure_time)
        if dt:
            return dt.strftime("%m-%d-%Y"), dt.strftime("%H:%M:%S")

        # 尝试 "HH:MM" 或 "HH:MM:SS"
        import re

        m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", departure_time.strip())
        if m:
            hh = int(m.group(1))
            mm = int(m.group(2))
            ss = int(m.group(3) or 0)
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                return date_str, f"{hh:02d}:{mm:02d}:{ss:02d}"

        return date_str, time_str

    @staticmethod
    def _seconds_to_minutes(seconds: Any) -> Optional[float]:
        """秒转分钟，容错处理。"""
        v = OneMapRoutesService._to_float(seconds)
        if v is None:
            return None
        return round(v / 60, 2)

    @staticmethod
    def _fare_sgd(fare: Any) -> Optional[float]:
        """pt 的 fare 是字符串（如 "1.77"），转为浮点。"""
        if fare is None:
            return None
        try:
            return round(float(fare), 2)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            f = float(value)
            return f if f == f else None  # 排除 NaN
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _walk_distance_from_steps(steps: List[Dict[str, Any]]) -> Optional[float]:
        total = sum(
            (s.get("distance_m") or 0)
            for s in steps
            if s.get("type") == "walk"
        )
        return total if total > 0 else None

    @staticmethod
    def _total_leg_distance(legs: Any) -> Optional[float]:
        if not isinstance(legs, list):
            return None
        total = 0.0
        has_value = False
        for leg in legs:
            if isinstance(leg, dict) and leg.get("distance") is not None:
                d = OneMapRoutesService._to_float(leg.get("distance"))
                if d is not None:
                    total += d
                    has_value = True
        return round(total, 1) if has_value else None

    @staticmethod
    def _summary_for_mode(route_mode: str) -> str:
        return {
            "driving": "驾车路线",
            "walking": "步行路线",
            "cycling": "骑行路线",
        }.get(route_mode, "OneMap 路线")

    @staticmethod
    def _pt_summary(legs: Any) -> str:
        """从 legs 提取公交线路名，生成摘要。"""
        if not isinstance(legs, list):
            return "公共交通路线"
        lines = []
        for leg in legs:
            if isinstance(leg, dict) and (leg.get("mode") or "").upper() in (
                "BUS",
                "SUBWAY",
                "RAIL",
                "TRAM",
            ):
                route = leg.get("route") or ""
                if route and route not in lines:
                    lines.append(route)
        if lines:
            return "公共交通（" + " / ".join(lines) + "）"
        return "公共交通路线"

    @staticmethod
    def _infer_step_type(title: Any, road_name: Any) -> str:
        """从指令标题/道路名推断步骤类型。"""
        t = (title or "").lower()
        if "walk" in t or "pedestrian" in t:
            return "walk"
        if "cycle" in t or "bike" in t:
            return "cycling"
        # drive/walk/cycle 的 route_instructions 默认都是对应模式的路段
        return "drive"


def _parse_iso(value: str) -> Optional[datetime]:
    """解析 ISO 8601 字符串为 datetime，失败返回 None。"""
    s = value.strip()
    # 去掉末尾的 "Z" 或时区后缀（简化处理）
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
