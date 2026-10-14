"""MCP Server 共享工具：统一输出结构与时间戳工具。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    """返回带时区的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


def make_result(
    status: str,
    data: Optional[Any] = None,
    source: str = "",
    error: Optional[str] = None,
    queried_at: Optional[str] = None,
) -> Dict[str, Any]:
    """构造统一的工具返回结构。

    字段说明：
    - status: "ok" | "partial" | "error"
    - data: 结构化数据，可为空
    - source: 数据来源标识（如 "mock" / "google_maps" / "weather_api"）
    - queried_at: 查询时间（UTC ISO）
    - error: 错误描述，无错误时为空字符串
    """
    return {
        "status": status,
        "data": data,
        "source": source,
        "queried_at": queried_at or utc_now_iso(),
        "error": error or "",
    }
