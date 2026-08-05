"""Pydantic 请求 / 响应模型。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------- 聊天 ----------

class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(
        default=None, description="会话 ID，为空则新建会话"
    )
    message: str = Field(..., description="用户消息")


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    needs_clarification: bool = False
    route_scores: List[Dict[str, Any]] = []
    selected_route: Optional[Dict[str, Any]] = None
    source: str = "mock"
    data_sources: Dict[str, Any] = {}
    errors: List[str] = []


# ---------- 会话 ----------

class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class SessionDetail(BaseModel):
    session_id: str
    title: str
    messages: List[Dict[str, Any]] = []


# ---------- 通勤计划 ----------

class CommuteSummary(BaseModel):
    id: int
    origin: str
    destination: str
    departure_time: Optional[str] = None
    mode: str
    selected_route_id: Optional[str] = None
    source: str
    created_at: str


class CommuteDetail(BaseModel):
    id: int
    origin: str
    destination: str
    departure_time: Optional[str] = None
    mode: str
    recommendation: str
    source: str
    created_at: str
    route_options: List[Dict[str, Any]] = []


# ---------- 用户偏好 ----------

class PreferencesUpdate(BaseModel):
    default_mode: Optional[str] = None
    prefer_fewer_transfers: Optional[float] = Field(default=None, ge=0, le=1)
    prefer_less_walking: Optional[float] = Field(default=None, ge=0, le=1)
    prefer_lower_cost: Optional[float] = Field(default=None, ge=0, le=1)
    prefer_shorter_time: Optional[float] = Field(default=None, ge=0, le=1)
    max_walk_m: Optional[int] = Field(default=None, ge=0)
    max_transfers: Optional[int] = Field(default=None, ge=0)


class PreferencesResponse(BaseModel):
    default_mode: str
    prefer_fewer_transfers: float
    prefer_less_walking: float
    prefer_lower_cost: float
    prefer_shorter_time: float
    max_walk_m: int
    max_transfers: int


# ---------- 统一错误 ----------

class ErrorResponse(BaseModel):
    detail: str
