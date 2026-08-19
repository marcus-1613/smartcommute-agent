"""数据库引擎与会话管理。"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from ..config import settings


def _build_engine():
    url = settings.database_url
    kwargs = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Session:
    """FastAPI 依赖：提供数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有表。"""
    from .entities import Base

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """轻量列迁移：为已存在的 SQLite 表补齐新增列（create_all 不会改已有表）。"""
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "messages" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("messages")}
    if "meta" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE messages ADD COLUMN meta JSON"))

