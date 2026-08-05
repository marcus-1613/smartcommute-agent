"""数据库模型（SQLAlchemy ORM）。

业务数据独立存储，与 LangGraph Checkpointer 分离。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), default="默认用户")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    preferences: Mapped["UserPreference"] = relationship(
        back_populates="user", uselist=False
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user"
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True
    )
    default_mode: Mapped[str] = mapped_column(String(32), default="transit")
    prefer_fewer_transfers: Mapped[float] = mapped_column(Float, default=0.5)
    prefer_less_walking: Mapped[float] = mapped_column(Float, default=0.5)
    prefer_lower_cost: Mapped[float] = mapped_column(Float, default=0.5)
    prefer_shorter_time: Mapped[float] = mapped_column(Float, default=0.5)
    max_walk_m: Mapped[int] = mapped_column(Integer, default=800)
    max_transfers: Mapped[int] = mapped_column(Integer, default=2)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="preferences")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(256), default="新会话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id")
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class CommutePlan(Base):
    __tablename__ = "commute_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id")
    )
    origin: Mapped[str] = mapped_column(String(256))
    destination: Mapped[str] = mapped_column(String(256))
    departure_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="transit")
    selected_route_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    recommendation: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    route_options: Mapped[list["RouteOption"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class RouteOption(Base):
    __tablename__ = "route_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("commute_plans.id"))
    route_key: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(256), default="")
    duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    fare_sgd: Mapped[float | None] = mapped_column(Float, nullable=True)
    walk_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    transfers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    feasible: Mapped[bool] = mapped_column(Boolean, default=True)

    plan: Mapped["CommutePlan"] = relationship(back_populates="route_options")


class ToolCallLog(Base):
    __tablename__ = "tool_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    error: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
