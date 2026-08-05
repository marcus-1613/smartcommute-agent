"""MCP Client 封装：连接 Mobility 与 Weather MCP Server，发现并调用工具。

使用官方 MCP Python SDK 的 stdio client，为每个工具调用独立建立连接，
保证生命周期可控，避免跨会话复用导致的状态问题。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 项目根目录：backend/app/services/mcp_client.py -> 上三级到项目根
_MCP_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp_servers")
)


class MCPToolClient:
    """管理 Mobility 与 Weather 两个 MCP Server 的客户端。

    每个 Server 以子进程方式通过 stdio 启动。
    """

    def __init__(self) -> None:
        self.mobility_script = os.path.join(_MCP_DIR, "mobility_server.py")
        self.weather_script = os.path.join(_MCP_DIR, "weather_server.py")
        # 优先使用当前解释器路径，避免 Windows 下裸 "python" 找不到
        self._python = os.environ.get(
            "SMARTCOMMUTE_PYTHON", sys.executable
        )

    async def _call_tool(
        self, server: str, tool: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用指定 server 的指定工具。"""
        script = (
            self.mobility_script if server == "mobility" else self.weather_script
        )
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Windows 下子进程默认使用系统代码页，需强制 UTF-8 以正确处理中文参数
            env = dict(os.environ)
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
            params = StdioServerParameters(
                command=self._python, args=[script], env=env
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments)
                    return _normalize_call_result(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("MCP 工具调用失败: %s.%s", server, tool)
            return {
                "status": "error",
                "data": None,
                "source": "mcp",
                "queried_at": "",
                "error": f"工具调用失败: {exc}",
            }

    async def search_place(self, query: str) -> Dict[str, Any]:
        return await self._call_tool("mobility", "search_place", {"query": query})

    async def get_routes(
        self,
        origin: str,
        destination: str,
        mode: str = "transit",
        departure_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        args: Dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "mode": mode,
        }
        if departure_time:
            args["departure_time"] = departure_time
        return await self._call_tool("mobility", "get_routes", args)

    async def get_traffic_incidents(
        self, area: Optional[str] = None
    ) -> Dict[str, Any]:
        args: Dict[str, Any] = {}
        if area:
            args["area"] = area
        return await self._call_tool("mobility", "get_traffic_incidents", args)

    async def get_weather_forecast(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        args: Dict[str, Any] = {"location": location}
        if forecast_time:
            args["forecast_time"] = forecast_time
        return await self._call_tool("weather", "get_weather_forecast", args)

    async def check_weather_risk(
        self, location: str, forecast_time: Optional[str] = None
    ) -> Dict[str, Any]:
        args: Dict[str, Any] = {"location": location}
        if forecast_time:
            args["forecast_time"] = forecast_time
        return await self._call_tool("weather", "check_weather_risk", args)


def _normalize_call_result(result: Any) -> Dict[str, Any]:
    """将 MCP CallToolResult 转为统一字典。"""
    content = getattr(result, "content", [])
    text_parts = []
    for item in content:
        text = getattr(item, "text", None)
        if text:
            text_parts.append(text)
    joined = "\n".join(text_parts).strip()
    if not joined:
        return {
            "status": "error",
            "data": None,
            "source": "mcp",
            "queried_at": "",
            "error": "工具返回为空",
        }
    # 工具返回的是 JSON 字符串，尝试解析
    import json

    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return {
            "status": "partial",
            "data": {"raw": joined},
            "source": "mcp",
            "queried_at": "",
            "error": "",
        }
