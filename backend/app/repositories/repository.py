"""数据访问层：封装业务实体的增删改查。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.entities import (
    CommutePlan,
    Conversation,
    Message,
    RouteOption,
    ToolCallLog,
    User,
    UserPreference,
)


DEFAULT_USER_ID = 1


def get_or_create_user(db: Session) -> User:
    user = db.get(User, DEFAULT_USER_ID)
    if user is None:
        user = User(id=DEFAULT_USER_ID, name="默认用户")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_or_create_preferences(db: Session) -> UserPreference:
    user = get_or_create_user(db)
    if user.preferences is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
        db.refresh(user)
    return user.preferences


def create_conversation(db: Session, session_id: str, title: str = "新会话") -> Conversation:
    user = get_or_create_user(db)
    conv = Conversation(id=session_id, user_id=user.id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, session_id: str) -> Optional[Conversation]:
    return db.get(Conversation, session_id)


def list_conversations(db: Session) -> List[Conversation]:
    stmt = (
        select(Conversation)
        .order_by(Conversation.updated_at.desc())
    )
    return list(db.scalars(stmt).all())


def add_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Message:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        meta=meta,
        created_at=now,
    )
    db.add(msg)
    conv = db.get(Conversation, conversation_id)
    if conv:
        conv.updated_at = now
        # 用首条用户消息作为标题
        if conv.title == "新会话" and role == "user":
            conv.title = content[:30]
    db.commit()
    db.refresh(msg)
    return msg


def list_messages(db: Session, conversation_id: str) -> List[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def create_commute_plan(
    db: Session,
    conversation_id: str,
    origin: str,
    destination: str,
    departure_time: Optional[str],
    mode: str,
    selected_route_id: Optional[str],
    recommendation: str,
    source: str,
    route_scores: List[Dict[str, Any]],
) -> CommutePlan:
    plan = CommutePlan(
        conversation_id=conversation_id,
        origin=origin,
        destination=destination,
        departure_time=departure_time,
        mode=mode,
        selected_route_id=selected_route_id,
        recommendation=recommendation,
        source=source,
    )
    db.add(plan)
    db.flush()

    for scored in route_scores:
        route = scored.get("route", {})
        opt = RouteOption(
            plan_id=plan.id,
            route_key=str(route.get("id", "")),
            summary=route.get("summary", ""),
            duration_min=route.get("duration_min"),
            fare_sgd=route.get("fare_sgd"),
            walk_distance_m=route.get("walk_distance_m"),
            transfers=route.get("transfers"),
            score=scored.get("score", 0.0),
            score_detail=scored.get("score_detail", {}),
            feasible=scored.get("feasible", True),
        )
        db.add(opt)

    db.commit()
    db.refresh(plan)
    return plan


def list_commute_plans(db: Session) -> List[CommutePlan]:
    stmt = select(CommutePlan).order_by(CommutePlan.created_at.desc())
    return list(db.scalars(stmt).all())


def get_commute_plan(db: Session, plan_id: int) -> Optional[CommutePlan]:
    return db.get(CommutePlan, plan_id)


def log_tool_call(
    db: Session,
    conversation_id: Optional[str],
    tool_name: str,
    status: str,
    error: str = "",
    duration_ms: Optional[int] = None,
) -> None:
    log = ToolCallLog(
        conversation_id=conversation_id,
        tool_name=tool_name,
        status=status,
        error=error,
        duration_ms=duration_ms,
    )
    db.add(log)
    db.commit()
