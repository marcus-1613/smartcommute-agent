"""LangGraph 工作流 State 定义。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class CommuteRequest(TypedDict, total=False):
    """解析后的通勤需求。"""

    origin: Optional[str]
    destination: Optional[str]
    departure_time: Optional[str]
    mode: str
    preferences: str
    hard_constraints: Dict[str, Any]


class AgentState(TypedDict, total=False):
    """Agent 工作流共享状态。"""

    # 消息历史（LangChain 消息对象）
    messages: List[Any]

    # 当前用户原始输入
    user_input: str

    # 解析后的通勤需求
    commute_request: CommuteRequest

    # 用户意图：commute（通勤/交通）| general（一般问题）
    intent: str

    # 缺失字段列表
    missing_fields: List[str]

    # 是否需要向用户澄清
    needs_clarification: bool

    # 澄清问题文本
    clarification_question: str

    # 路线结果（原始）
    route_results: Optional[Dict[str, Any]]

    # 天气结果
    weather_result: Optional[Dict[str, Any]]

    # 交通事件
    traffic_incidents: Optional[Dict[str, Any]]

    # 数据来源汇总（各数据源分别标记来源与状态）
    data_sources: Dict[str, Any]

    # 路线评分结果
    route_scores: List[Dict[str, Any]]

    # 选中的路线
    selected_route: Optional[Dict[str, Any]]

    # 最终回复文本
    final_response: str

    # LLM 数据来源标识（deepseek | mock）
    llm_source: str

    # 重试次数
    retry_count: int

    # 错误信息
    errors: List[str]
