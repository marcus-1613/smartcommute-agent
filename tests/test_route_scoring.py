"""路线评分确定性单元测试。"""
from __future__ import annotations

import pytest

from app.services.route_scoring import (
    UserPreferences,
    score_routes,
    ScoringWeights,
)


def make_route(route_id, duration, fare, walk, transfers, summary="r"):
    return {
        "id": route_id,
        "summary": summary,
        "mode": "transit",
        "duration_min": duration,
        "fare_sgd": fare,
        "walk_distance_m": walk,
        "transfers": transfers,
    }


def test_score_routes_orders_by_score():
    routes = [
        make_route("a", 30, 2.0, 500, 0, "快"),
        make_route("b", 60, 1.0, 100, 1, "慢"),
    ]
    scored = score_routes(routes)
    assert len(scored) == 2
    # 快且便宜换乘少的路线应排前
    assert scored[0]["route"]["id"] == "a"
    assert scored[0]["score"] >= scored[1]["score"]


def test_score_routes_deterministic():
    routes = [make_route("a", 30, 2.0, 500, 0)]
    s1 = score_routes(routes)
    s2 = score_routes(routes)
    assert s1[0]["score"] == s2[0]["score"]


def test_hard_constraint_filters_transfers():
    routes = [
        make_route("a", 30, 2.0, 500, 0, "直达"),
        make_route("b", 28, 1.0, 100, 2, "多换乘"),
    ]
    scored = score_routes(routes, hard_constraints={"max_transfers": 1})
    # 多换乘路线应标记不可行
    by_id = {s["route"]["id"]: s for s in scored}
    assert by_id["b"]["feasible"] is False
    assert by_id["a"]["feasible"] is True
    # 可行路线排前
    assert scored[0]["route"]["id"] == "a"


def test_missing_metric_uses_neutral():
    routes = [
        {"id": "a", "summary": "x", "duration_min": 30, "fare_sgd": None,
         "walk_distance_m": None, "transfers": None},
        {"id": "b", "summary": "y", "duration_min": 30, "fare_sgd": 2.0,
         "walk_distance_m": 500, "transfers": 1},
    ]
    scored = score_routes(routes)
    # 不因缺失指标报错
    assert len(scored) == 2


def test_empty_routes_returns_empty():
    assert score_routes([]) == []


def test_weights_normalize():
    prefs = UserPreferences()
    w = prefs.effective_weights()
    total = (
        w.duration + w.fare + w.walking + w.transfers
        + w.weather_risk + w.traffic
    )
    assert abs(total - 1.0) < 1e-6
