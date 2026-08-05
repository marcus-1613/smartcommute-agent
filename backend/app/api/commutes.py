"""历史通勤计划 API 路由。"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..schemas.api import CommuteDetail, CommuteSummary
from ..repositories import repository as repo

router = APIRouter(tags=["commutes"])


@router.get("/commutes", response_model=List[CommuteSummary])
def list_commutes(db: Session = Depends(get_db)):
    plans = repo.list_commute_plans(db)
    return [
        CommuteSummary(
            id=p.id,
            origin=p.origin,
            destination=p.destination,
            departure_time=p.departure_time,
            mode=p.mode,
            selected_route_id=p.selected_route_id,
            source=p.source,
            created_at=p.created_at.isoformat(),
        )
        for p in plans
    ]


@router.get("/commutes/{commute_id}", response_model=CommuteDetail)
def get_commute(commute_id: int, db: Session = Depends(get_db)):
    plan = repo.get_commute_plan(db, commute_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="通勤计划不存在")
    route_options = [
        {
            "route_key": r.route_key,
            "summary": r.summary,
            "duration_min": r.duration_min,
            "fare_sgd": r.fare_sgd,
            "walk_distance_m": r.walk_distance_m,
            "transfers": r.transfers,
            "score": r.score,
            "score_detail": r.score_detail,
            "feasible": r.feasible,
        }
        for r in plan.route_options
    ]
    return CommuteDetail(
        id=plan.id,
        origin=plan.origin,
        destination=plan.destination,
        departure_time=plan.departure_time,
        mode=plan.mode,
        recommendation=plan.recommendation,
        source=plan.source,
        created_at=plan.created_at.isoformat(),
        route_options=route_options,
    )
