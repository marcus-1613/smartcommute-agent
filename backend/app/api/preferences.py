"""用户偏好 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..schemas.api import PreferencesResponse, PreferencesUpdate
from ..repositories import repository as repo

router = APIRouter(tags=["preferences"])


@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(db: Session = Depends(get_db)):
    prefs = repo.get_or_create_preferences(db)
    return PreferencesResponse(
        default_mode=prefs.default_mode,
        prefer_fewer_transfers=prefs.prefer_fewer_transfers,
        prefer_less_walking=prefs.prefer_less_walking,
        prefer_lower_cost=prefs.prefer_lower_cost,
        prefer_shorter_time=prefs.prefer_shorter_time,
        max_walk_m=prefs.max_walk_m,
        max_transfers=prefs.max_transfers,
    )


@router.put("/preferences", response_model=PreferencesResponse)
def update_preferences(
    req: PreferencesUpdate, db: Session = Depends(get_db)
):
    prefs = repo.get_or_create_preferences(db)
    updates = req.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(prefs, key, value)
    db.commit()
    db.refresh(prefs)
    return PreferencesResponse(
        default_mode=prefs.default_mode,
        prefer_fewer_transfers=prefs.prefer_fewer_transfers,
        prefer_less_walking=prefs.prefer_less_walking,
        prefer_lower_cost=prefs.prefer_lower_cost,
        prefer_shorter_time=prefs.prefer_shorter_time,
        max_walk_m=prefs.max_walk_m,
        max_transfers=prefs.max_transfers,
    )
