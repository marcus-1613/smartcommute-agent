"""新加坡 LTA DataMall 交通事件适配器。

实现交通事件查询，调用 LTA DataMall 的 Traffic Incidents API。
需要 AccountKey（通过 HTTP 头 AccountKey 传递）。

注意：
- AccountKey 仅从环境变量读取，不写入日志。
- 设置超时、错误处理与日志脱敏。
- 返回统一结构，source 固定为 "lta_datamall"。
- 无 Key 时返回 status=error（明确错误），绝不伪造事件数据。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

from shared.result import make_result

logger = logging.getLogger(__name__)

# LTA DataMall Traffic Incidents 端点（交通事件）
_TRAFFIC_INCIDENTS_ENDPOINT = (
    "http://datamall2.mytransport.sg/ltaodataservice/TrafficIncidents"
)


class LTATrafficService:
    """基于 LTA DataMall 的真实交通事件服务。"""

    source_name = "lta_datamall"

    def __init__(
        self,
        account_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.account_key = account_key or os.getenv("LTA_ACCOUNT_KEY", "")
        self.endpoint = endpoint or os.getenv(
            "LTA_TRAFFIC_INCIDENTS_ENDPOINT", _TRAFFIC_INCIDENTS_ENDPOINT
        )
        self.timeout = timeout

    def get_traffic_incidents(self, area: Optional[str] = None) -> Dict[str, Any]:
        """查询当前交通事件。

        LTA Traffic Incidents 返回新加坡全岛事件列表，本实现做简单区域过滤。
        """
        if not self.account_key:
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error="未配置 LTA_ACCOUNT_KEY",
            )

        headers = {
            "AccountKey": self.account_key,
            "Accept": "application/json",
        }
        try:
            resp = httpx.get(
                self.endpoint, headers=headers, timeout=self.timeout
            )
        except httpx.TimeoutException:
            logger.error("LTA 交通事件请求超时")
            return make_result(
                "error", data=None, source=self.source_name, error="请求超时"
            )
        except httpx.HTTPError as exc:
            logger.error("LTA 交通事件请求失败：%s", type(exc).__name__)
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"网络错误：{type(exc).__name__}",
            )

        if resp.status_code != 200:
            logger.error("LTA 交通事件返回 %s", resp.status_code)
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"API 返回 {resp.status_code}",
            )

        try:
            payload = resp.json()
            incidents = self._convert_incidents(payload, area)
            return make_result(
                "ok",
                {"incidents": incidents},
                source=self.source_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("LTA 交通事件响应解析失败")
            return make_result(
                "error",
                data=None,
                source=self.source_name,
                error=f"响应解析失败：{exc}",
            )

    def _convert_incidents(
        self, payload: Dict[str, Any], area: Optional[str]
    ) -> list:
        """将 LTA 响应转换为统一交通事件模型。"""
        raw = payload.get("value", [])
        incidents = []
        for item in raw:
            incident = {
                "id": item.get("IncidentID") or item.get("id"),
                "type": item.get("Type") or item.get("type"),
                "line": None,
                "description": item.get("Message") or item.get("Summary", ""),
                "severity": self._map_severity(item.get("Type")),
                "area": self._extract_area(item),
            }
            if area and area.lower() not in (incident["area"] or "").lower():
                continue
            incidents.append(incident)
        return incidents

    @staticmethod
    def _map_severity(incident_type: Optional[str]) -> str:
        """将 LTA 事件类型粗略映射为严重程度。"""
        t = (incident_type or "").lower()
        if "accident" in t or "accident" in t:
            return "high"
        if "roadworks" in t or "road work" in t or "vehicle breakdown" in t:
            return "medium"
        return "low"

    @staticmethod
    def _extract_area(item: Dict[str, Any]) -> str:
        """尽量提取区域/道路名，缺省为空字符串。"""
        return item.get("RoadName") or item.get("Location") or ""
