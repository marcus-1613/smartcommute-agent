"""Mobility MCP Server：地点查询、路线查询、交通事件。

独立启动，暴露以下工具：
- search_place
- get_routes
- get_traffic_incidents

数据源选择：
- 路线（search_place / get_routes）：
  - 有 ONEMAP_TOKEN：OneMap Routing API（真实路线，官方免费）
  - 否则有 GOOGLE_MAPS_API_KEY：Google Maps Routes API（真实路线）
  - 否则：Mock 演示数据（明确标记 source=mock）
- 交通事件（get_traffic_incidents）与路线解耦：
  - 有 LTA_ACCOUNT_KEY：LTA DataMall（真实事件）
  - 无 Key：Mock 演示事件（明确标记 source=mock）
"""
from __future__ import annotations

import os
import sys
from typing import Optional

# 保证可导入 shared 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env（从项目根目录），使子进程能读取 API Key
try:
    from dotenv import load_dotenv

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except Exception:  # noqa: BLE001
    pass

from mcp.server.fastmcp import FastMCP  # noqa: E402
from shared.mock_mobility import MockMobilityService  # noqa: E402
from shared.google_maps_service import GoogleMapsRoutesService  # noqa: E402
from shared.onemap_service import OneMapRoutesService  # noqa: E402
from shared.lta_service import LTATrafficService  # noqa: E402
from shared.mobility_service import MobilityService  # noqa: E402

mcp = FastMCP("mobility")


def _build_route_service() -> MobilityService:
    """根据环境变量选择路线数据源（OneMap → Google Maps → Mock）。"""
    onemap_token = os.getenv("ONEMAP_TOKEN", "")
    if onemap_token:
        return OneMapRoutesService(token=onemap_token)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if api_key:
        return GoogleMapsRoutesService(api_key=api_key)
    return MockMobilityService()


def _build_traffic_service():
    """根据环境变量选择交通事件数据源（LTA 或 Mock）。

    交通事件与路线解耦：即使没有 Google Maps Key，
    只要配置了 LTA_ACCOUNT_KEY 也能返回真实交通事件。
    """
    lta_key = os.getenv("LTA_ACCOUNT_KEY", "")
    if lta_key:
        return LTATrafficService(account_key=lta_key)
    return MockMobilityService()


_route_service = _build_route_service()
_traffic_service = _build_traffic_service()


@mcp.tool()
def search_place(query: str) -> dict:
    """查询或标准化一个新加坡地名。

    Args:
        query: 地点名称（中文或英文），如 "Jurong East" 或 "裕廊东"。
    """
    return _route_service.search_place(query)


@mcp.tool()
def get_routes(
    origin: str,
    destination: str,
    mode: str = "transit",
    departure_time: Optional[str] = None,
) -> dict:
    """查询出发地到目的地的候选路线。

    Args:
        origin: 出发地名称。
        destination: 目的地名称。
        mode: 交通方式，可选 "transit"（公共交通，默认）、"driving"（驾车）、"all"。
        departure_time: 出发时间，ISO 8601 字符串，如 "2026-10-15T08:00:00+08:00"。
    """
    return _route_service.get_routes(origin, destination, mode, departure_time)


@mcp.tool()
def get_traffic_incidents(area: Optional[str] = None) -> dict:
    """查询道路交通或公共交通事件。

    Args:
        area: 可选，按区域过滤，如 "乌节路"。
    """
    return _traffic_service.get_traffic_incidents(area)


if __name__ == "__main__":
    mcp.run()
