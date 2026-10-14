"""会话 API 路由。"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..schemas.api import SessionDetail, SessionSummary
from ..repositories import repository as repo

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=List[SessionSummary])
def list_sessions(db: Session = Depends(get_db)):
    convs = repo.list_conversations(db)
    return [
        SessionSummary(
            session_id=c.id,
            title=c.title,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
            message_count=len(c.messages),
        )
        for c in convs
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, db: Session = Depends(get_db)):
    conv = repo.get_conversation(db, session_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = [
        {
            "role": m.role,
            "content": m.content,
            "meta": m.meta,
            "created_at": m.created_at.isoformat(),
        }
        for m in conv.messages
    ]
    return SessionDetail(
        session_id=conv.id,
        title=conv.title,
        messages=messages,
    )
