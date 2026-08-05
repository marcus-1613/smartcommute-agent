"""Mobility 数据源服务：地点解析、路线查询、交通事件。

采用适配器模式：MobilityService 对外提供统一接口，
底层可切换为 Mock 实现或真实 API（Google Maps / LTA）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class MobilityService:
    """地点、路线、交通事件查询服务。"""

    def search_place(self, query: str) -> Dict[str, Any]:
        raise NotImplementedError

    def get_routes(
        self,
        origin: str,
        destination: str,
        mode: str = "transit",
        departure_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def get_traffic_incidents(self, area: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError
