"""路线评分：确定性计算，不依赖大模型。

评分维度：耗时、费用、步行距离、换乘次数、天气风险、交通异常。
支持硬约束（用户明确限制）与软偏好（权重偏好）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScoringWeights:
    """各指标权重，可配置。权重越高，该指标越重要。"""

    duration: float = 0.30
    fare: float = 0.20
    walking: float = 0.15
    transfers: float = 0.15
    weather_risk: float = 0.10
    traffic: float = 0.10


@dataclass
class UserPreferences:
    """用户软偏好（数值 0~1 表示重视程度）。"""

    prefer_fewer_transfers: float = 0.5
    prefer_less_walking: float = 0.5
    prefer_lower_cost: float = 0.5
    prefer_shorter_time: float = 0.5

    def effective_weights(self) -> ScoringWeights:
        """根据用户偏好微调默认权重。"""
        w = ScoringWeights()
        w.duration *= 1.0 + self.prefer_shorter_time * 0.4
        w.fare *= 1.0 + self.prefer_lower_cost * 0.4
        w.walking *= 1.0 + self.prefer_less_walking * 0.4
        w.transfers *= 1.0 + self.prefer_fewer_transfers * 0.4
        total = (
            w.duration + w.fare + w.walking + w.transfers
            + w.weather_risk + w.traffic
        )
        # 归一化权重
        w.duration /= total
        w.fare /= total
        w.walking /= total
        w.transfers /= total
        w.weather_risk /= total
        w.traffic /= total
        return w


def _normalize_min(value: Optional[float], min_v: float, max_v: float) -> float:
    """归一化：值越小越好。缺失值返回中性 0.5。"""
    if value is None:
        return 0.5
    if max_v == min_v:
        return 0.5
    return (value - min_v) / (max_v - min_v)


def _normalize_max(value: Optional[float], min_v: float, max_v: float) -> float:
    """归一化：值越大越好。缺失值返回中性 0.5。"""
    return 1.0 - _normalize_min(value, min_v, max_v)


def score_routes(
    routes: List[Dict[str, Any]],
    weather_risk_level: Optional[str] = None,
    traffic_incidents: Optional[List[Dict[str, Any]]] = None,
    preferences: Optional[UserPreferences] = None,
    hard_constraints: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """对候选路线打分，返回带评分明细的列表（按分数降序）。

    参数：
        routes: 候选路线列表。
        weather_risk_level: "low"|"medium"|"high"|None。
        traffic_incidents: 交通事件列表。
        preferences: 用户软偏好。
        hard_constraints: 硬约束，如 {"max_transfers": 1, "max_walk_m": 800}。
    """
    if not routes:
        return []

    prefs = preferences or UserPreferences()
    weights = prefs.effective_weights()
    constraints = hard_constraints or {}

    # 天气风险数值化
    weather_map = {"low": 0.0, "medium": 0.5, "high": 1.0, None: 0.0}
    weather_score = weather_map.get(weather_risk_level, 0.0)

    # 交通异常数值化：按严重程度统计
    traffic_score = 0.0
    if traffic_incidents:
        sev_map = {"low": 0.3, "medium": 0.6, "high": 1.0}
        traffic_score = max(
            (sev_map.get(i.get("severity", "low"), 0.3) for i in traffic_incidents),
            default=0.0,
        )

    # 提取指标范围用于归一化
    durations = [r.get("duration_min") for r in routes]
    fares = [r.get("fare_sgd") for r in routes]
    walks = [r.get("walk_distance_m") for r in routes]
    transfers = [r.get("transfers") for r in routes]

    def _range(vals):
        valid = [v for v in vals if v is not None]
        return (min(valid), max(valid)) if valid else (0, 0)

    d_min, d_max = _range(durations)
    f_min, f_max = _range(fares)
    w_min, w_max = _range(walks)
    t_min, t_max = _range(transfers)

    scored = []
    for route in routes:
        # 硬约束过滤
        constraint_violations = []
        if "max_transfers" in constraints:
            if route.get("transfers", 0) > constraints["max_transfers"]:
                constraint_violations.append(
                    f"换乘次数 {route.get('transfers')} 超过限制 {constraints['max_transfers']}"
                )
        if "max_walk_m" in constraints:
            if route.get("walk_distance_m", 0) > constraints["max_walk_m"]:
                constraint_violations.append(
                    f"步行距离 {route.get('walk_distance_m')}m 超过限制 {constraints['max_walk_m']}m"
                )
        if "max_duration_min" in constraints:
            if route.get("duration_min", 0) > constraints["max_duration_min"]:
                constraint_violations.append(
                    f"耗时 {route.get('duration_min')} 分钟超过限制 {constraints['max_duration_min']} 分钟"
                )

        # 各指标评分（0~1，越高越好）
        s_duration = _normalize_max(route.get("duration_min"), d_min, d_max)
        s_fare = _normalize_max(route.get("fare_sgd"), f_min, f_max)
        s_walking = _normalize_max(route.get("walk_distance_m"), w_min, w_max)
        s_transfers = _normalize_max(route.get("transfers"), t_min, t_max)
        s_weather = 1.0 - weather_score
        s_traffic = 1.0 - traffic_score

        total = (
            weights.duration * s_duration
            + weights.fare * s_fare
            + weights.walking * s_walking
            + weights.transfers * s_transfers
            + weights.weather_risk * s_weather
            + weights.traffic * s_traffic
        )

        detail = {
            "duration": round(s_duration, 3),
            "fare": round(s_fare, 3),
            "walking": round(s_walking, 3),
            "transfers": round(s_transfers, 3),
            "weather_risk": round(s_weather, 3),
            "traffic": round(s_traffic, 3),
        }

        scored.append(
            {
                "route": route,
                "score": round(total, 4),
                "score_detail": detail,
                "constraint_violations": constraint_violations,
                "feasible": len(constraint_violations) == 0,
            }
        )

    # 排序：可行优先，再按分数降序
    scored.sort(key=lambda x: (x["feasible"], x["score"]), reverse=True)
    return scored
