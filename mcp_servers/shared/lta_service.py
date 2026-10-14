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
import re
from typing import Any, Dict, Optional

import httpx

from shared.result import make_result

logger = logging.getLogger(__name__)

# 从 Message 中提取道路名：匹配 "on <道路名>" 后的道路缩写/名称。
# 新加坡道路常见缩写：PIE、CTE、AYE、SLE、TPE、BKE、KPE、ECP、MCE 等，
# 或完整道路名（如 "Bukit Timah Road"）。
# 注意：缩写分支仅匹配全大写（避免误匹配 "Bukit" 等完整道路名开头）。
_ROADNAME_RE = re.compile(
    r"\bon\s+([A-Z]{2,4}|(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+Road))"
)

# LTA DataMall Traffic Incidents 端点（交通事件）
# 注意：需使用 HTTPS（HTTP 已返回 301 重定向），路径无连字符。
_TRAFFIC_INCIDENTS_ENDPOINT = (
    "https://datamall2.mytransport.sg/ltaodataservice/TrafficIncidents"
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
                self.endpoint,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
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
        """将 LTA 响应转换为统一交通事件模型。

        对非预期结构（value 缺失/非列表/含非 dict 元素）做容错，
        不抛异常，返回空列表或可转换的部分。
        """
        raw = payload.get("value", []) if isinstance(payload, dict) else []
        if not isinstance(raw, list):
            return []
        incidents = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            message = item.get("Message") or item.get("Summary", "")
            incident = {
                # LTA Traffic Incidents 无唯一 ID 字段，用索引生成稳定标识
                "id": item.get("IncidentID") or item.get("id") or f"lta-{idx}",
                "type": item.get("Type") or item.get("type"),
                "line": None,
                "description": message,
                "severity": self._map_severity(item.get("Type")),
                "area": self._extract_area(item),
                # LTA 提供经纬度，补充进结果（无则 None）
                "latitude": item.get("Latitude"),
                "longitude": item.get("Longitude"),
            }
            if area and area.lower() not in (incident["area"] or "").lower():
                continue
            incidents.append(incident)
        return incidents

    @staticmethod
    def _map_severity(incident_type: Optional[str]) -> str:
        """将 LTA 事件类型粗略映射为严重程度。

        LTA Traffic Incidents 的 Type 实际取值（真实数据）：
        - "Accident"（事故）→ high
        - "Roadwork"（道路施工，注意是一个词）、"Vehicle Breakdown" → medium
        - "Heavy Traffic" 等 → low
        """
        t = (incident_type or "").lower()
        if "accident" in t:
            return "high"
        if "roadwork" in t or "road work" in t or "vehicle breakdown" in t:
            return "medium"
        return "low"

    @staticmethod
    def _extract_area(item: Dict[str, Any]) -> str:
        """尽量提取区域/道路名，缺省为空字符串。

        LTA Traffic Incidents 无独立区域字段，道路名在 Message 文本中
        （如 "Heavy Traffic on PIE (towards Tuas) ..."），用正则提取。
        """
        if not isinstance(item, dict):
            return ""
        area = item.get("RoadName") or item.get("Location")
        if area:
            return area
        # 从 Message 中提取 "on X" 后的道路名
        message = item.get("Message") or ""
        m = _ROADNAME_RE.search(message)
        return m.group(1) if m else ""
