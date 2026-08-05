"""LangGraph Checkpointer 工厂：SQLite 持久化的异步 checkpointer。

Checkpointer 用于保存工作流会话状态，支持通过 thread_id 恢复多轮会话。
与业务数据库（SQLAlchemy）分离存储。

使用 AsyncSqliteSaver（异步），并在应用关闭时正确关闭连接，
避免 Windows 下进程退出时的资源清理问题。
"""
from __future__ import annotations

import os
from typing import Optional

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# 项目根目录：backend/app/agent/checkpointer.py -> 上四级到项目根
_CHECKPOINT_PATH = os.path.join(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    ),
    "smartcommute.checkpoint.sqlite",
)


class CheckpointerManager:
    """管理 AsyncSqliteSaver 的创建与关闭。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.environ.get(
            "SMARTCOMMUTE_CHECKPOINT_PATH", _CHECKPOINT_PATH
        )
        self._saver: Optional[AsyncSqliteSaver] = None
        self._conn = None

    async def get_saver(self) -> Optional[AsyncSqliteSaver]:
        """懒加载并初始化 AsyncSqliteSaver。"""
        if self._saver is None:
            import aiosqlite

            self._conn = await aiosqlite.connect(self.path)
            self._saver = AsyncSqliteSaver(self._conn)
            await self._saver.setup()
        return self._saver

    async def close(self) -> None:
        """关闭底层 aiosqlite 连接，保证优雅退出。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            self._saver = None


# 向后兼容：保留 create_checkpointer 函数
async def create_checkpointer(path: Optional[str] = None) -> AsyncSqliteSaver:
    """创建并初始化一个异步 SQLite checkpointer。

    注意：调用方需负责在应用关闭时关闭连接。
    推荐使用 CheckpointerManager 管理生命周期。
    """
    manager = CheckpointerManager(path)
    return await manager.get_saver()
