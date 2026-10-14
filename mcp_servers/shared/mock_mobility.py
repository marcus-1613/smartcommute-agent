"""Mock Mobility 服务实现：基于新加坡静态数据生成演示路线。

所有结果 source 标记为 "mock"，绝不冒充实时数据。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.result import make_result
from shared.singapore_data import PLACES, MRT_LINES
from shared.mobility_service import MobilityService


class MockMobilityService(MobilityService):
    """使用静态数据 + 规则生成演示路线与交通事件。"""

    source_name = "mock"

    def search_place(self, query: str) -> Dict[str, Any]:
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
            error=f"未找到地点：{query}",
        )

    def get_routes(
        self,
        origin: str,
        destination: str,
        mode: str = "transit",
        departure_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        o = self.search_place(origin)
        d = self.search_place(destination)
        if o["status"] != "ok" or d["status"] != "ok":
            missing = origin if o["status"] != "ok" else destination
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"无法解析地点：{missing}",
            )

        o_name = o["data"]["name"]
        d_name = d["data"]["name"]

        # 生成候选路线（演示用，确定性输出）
        routes = self._build_routes(o_name, d_name, mode)
        return make_result(
            "ok",
            {
                "origin": o_name,
                "destination": d_name,
                "mode": mode,
                "departure_time": departure_time,
                "routes": routes,
            },
            source=self.source_name,
        )

    def get_traffic_incidents(self, area: Optional[str] = None) -> Dict[str, Any]:
        # 固定演示交通事件，明确为模拟数据
        incidents = [
            {
                "id": "mock-inc-1",
                "type": "地铁延误",
                "line": "东西线 (EWL)",
                "description": "裕廊东至政府大厦方向信号系统例行维护，预计延误 5 分钟",
                "severity": "low",
                "area": "裕廊东",
            },
            {
                "id": "mock-inc-2",
                "type": "交通拥堵",
                "line": None,
                "description": "乌节路周边道路车流较大，驾车可能额外 10 分钟",
                "severity": "medium",
                "area": "乌节路",
            },
        ]
        if area:
            incidents = [
                i for i in incidents if area.lower() in i["area"].lower()
            ]
        return make_result(
            "ok",
            {"incidents": incidents},
            source=self.source_name,
        )

    def _build_routes(
        self, o_name: str, d_name: str, mode: str
    ) -> List[Dict[str, Any]]:
        """按规则生成 2~3 条演示路线，字段与真实 API 对齐。"""
        # 基础距离估算（演示值）
        base_duration = 35  # 分钟
        routes: List[Dict[str, Any]] = []

        # 路线 1：最少换乘（推荐默认）
        routes.append(
            {
                "id": "route-direct",
                "summary": "地铁直达，换乘少",
                "mode": "transit",
                "steps": [
                    {"type": "walk", "description": f"步行至{o_name}站", "distance_m": 300, "duration_min": 4},
                    {"type": "transit", "description": f"乘坐地铁由{o_name}前往{d_name}", "line": "东西线 (EWL)", "duration_min": base_duration},
                    {"type": "walk", "description": f"步行至目的地", "distance_m": 400, "duration_min": 5},
                ],
                "duration_min": base_duration + 9,
                "fare_sgd": 1.9,
                "walk_distance_m": 700,
                "transfers": 0,
            }
        )

        # 路线 2：更少步行（换乘一次）
        routes.append(
            {
                "id": "route-less-walk",
                "summary": "步行最少，换乘 1 次",
                "mode": "transit",
                "steps": [
                    {"type": "walk", "description": f"步行至{o_name}站", "distance_m": 120, "duration_min": 2},
                    {"type": "transit", "description": f"乘坐地铁由{o_name}至政府大厦", "line": "东西线 (EWL)", "duration_min": 20},
                    {"type": "transfer", "description": "在政府大厦换乘", "duration_min": 4},
                    {"type": "transit", "description": f"乘坐地铁由政府大厦至{d_name}", "line": "南北线 (NSL)", "duration_min": 15},
                    {"type": "walk", "description": "步行至目的地", "distance_m": 150, "duration_min": 2},
                ],
                "duration_min": 43,
                "fare_sgd": 1.5,
                "walk_distance_m": 270,
                "transfers": 1,
            }
        )

        # 路线 3：驾车（若允许）
        if mode in ("driving", "all"):
            routes.append(
                {
                    "id": "route-drive",
                    "summary": "驾车，最快但费用较高",
                    "mode": "driving",
                    "steps": [
                        {"type": "drive", "description": f"驾车由{o_name}前往{d_name}", "duration_min": 22},
                    ],
                    "duration_min": 22,
                    "fare_sgd": 12.0,
                    "walk_distance_m": 0,
                    "transfers": 0,
                }
            )

        return routes
