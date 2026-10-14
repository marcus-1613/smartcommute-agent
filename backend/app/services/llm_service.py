"""LLM 服务封装：DeepSeek 真实调用 + Mock 降级。

职责：
- 通过 OpenAI 兼容接口调用 DeepSeek。
- 提供结构化 JSON 输出（需求解析）与自由文本（推荐解释）。
- 调用失败时按配置降级为规则/模板实现，并明确标记数据来源。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LLMService:
    """抽象 LLM 服务接口。"""

    source_name = "llm"

    def parse_commute(self, user_input: str, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """解析自然语言为通勤需求字段。返回 dict，含 source 标记。"""
        raise NotImplementedError

    def explain_recommendation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成推荐解释。返回 dict，含 text 与 source。"""
        raise NotImplementedError

    def chat_free_text(self, user_input: str) -> Dict[str, Any]:
        """通用自由问答：不限定通勤领域，直接生成文本回答。

        用于非通勤意图（一般知识、问候、闲聊等）的直接回答。
        返回 dict，含 text 与 source；失败时 text 为空且 ok=False。
        """
        raise NotImplementedError

    def classify_intent(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """判断用户输入是否为通勤/交通意图。

        返回 dict，含 intent（"commute" | "general"）与 source；失败时默认 commute（走原流程）。
        """
        raise NotImplementedError


class DeepSeekLLMService(LLMService):
    """基于 DeepSeek 的真实 LLM 实现。"""

    source_name = "deepseek"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    def _chat_json(self, messages, max_tokens: int = 400) -> Optional[Dict[str, Any]]:
        """调用模型并解析 JSON 输出。失败返回 None。"""
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=0,
        )
        content = resp.choices[0].message.content.strip()
        # 去除可能的 markdown 代码块包裹
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)

    def _chat_text(self, messages, max_tokens: int = 600) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    def parse_commute(self, user_input: str, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        existing = existing or {}
        prompt = (
            "你是新加坡通勤助手，负责从用户输入中提取通勤需求字段。\n"
            "已有字段（多轮对话累积，优先保留）：" + json.dumps(existing, ensure_ascii=False) + "\n"
            "用户输入：" + user_input + "\n"
            "请提取或更新以下字段，缺失的用空字符串，已有值不要覆盖为空：\n"
            '{"origin": "出发地", "destination": "目的地", '
            '"departure_time": "出发时间(如 08:00)", "mode": "transit|driving", '
            '"preferences": "偏好描述", "max_transfers": 整数或null, "max_walk_m": 整数或null}\n'
            "只输出 JSON，不要输出其他内容。"
        )
        try:
            data = self._chat_json(
                [{"role": "user", "content": prompt}], max_tokens=400
            )
            if not isinstance(data, dict):
                raise ValueError("非 dict 返回")
            # 合并：已有字段优先，新字段填充
            merged = dict(existing)
            for key in ("origin", "destination", "departure_time", "mode", "preferences"):
                val = data.get(key)
                if val and not merged.get(key):
                    merged[key] = val
            # 硬约束
            constraints = dict(merged.get("hard_constraints") or {})
            if data.get("max_transfers") is not None:
                constraints["max_transfers"] = int(data["max_transfers"])
            if data.get("max_walk_m") is not None:
                constraints["max_walk_m"] = int(data["max_walk_m"])
            if constraints:
                merged["hard_constraints"] = constraints
            return {"ok": True, "data": merged, "source": self.source_name, "error": ""}
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek 解析失败，降级规则解析：%s", exc)
            return {"ok": False, "data": existing, "source": "mock", "error": str(exc)}

    def explain_recommendation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            "你是新加坡通勤助手。基于以下路线评分结果，用简洁中文解释推荐原因（100字以内），"
            "不要编造数据，只基于提供的事实。\n"
            + json.dumps(context, ensure_ascii=False)
        )
        try:
            text = self._chat_text([{"role": "user", "content": prompt}], max_tokens=600)
            return {"ok": True, "text": text, "source": self.source_name, "error": ""}
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek 解释生成失败：%s", exc)
            return {"ok": False, "text": "", "source": "mock", "error": str(exc)}

    def chat_free_text(self, user_input: str) -> Dict[str, Any]:
        """通用自由问答：不限定通勤领域，直接回答用户问题。"""
        prompt = (
            "你是一个友好、专业的 AI 助手。请直接、简洁地回答用户的问题。\n"
            "用户问题：" + user_input + "\n"
            "请用中文回答。"
        )
        try:
            text = self._chat_text([{"role": "user", "content": prompt}], max_tokens=800)
            if not text:
                return {"ok": False, "text": "", "source": self.source_name, "error": "模型返回空内容"}
            return {"ok": True, "text": text, "source": self.source_name, "error": ""}
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek 通用问答失败：%s", exc)
            return {"ok": False, "text": "", "source": self.source_name, "error": str(exc)}

    def classify_intent(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """判断输入是否为通勤/交通意图。失败时默认 commute（走原流程，不阻断）。

        context 为当前已累积的通勤上下文（origin/destination 等），
        用于在多轮对话中区分「路线调整/补充」（commute）与「话题跳转」（general）。
        """
        ctx_line = ""
        if context and (context.get("origin") or context.get("destination")):
            ctx_line = (
                "当前对话已有通勤上下文（出发地/目的地等）："
                + json.dumps(context, ensure_ascii=False)
                + "\n"
            )
        prompt = (
            "判断下面这句话的意图。\n"
            + ctx_line
            + "如果这句话是在询问或调整「通勤/交通出行」相关事项（问路、规划路线、查询交通方式、"
            "天气对出行的影响、交通路况、地铁公交、调整路线/偏好等），输出 {\"intent\": \"commute\"}。\n"
            "如果这句话是普通知识、概念解释、问候、闲聊或与出行无关的其他话题（即使前面聊过通勤），"
            "输出 {\"intent\": \"general\"}。\n"
            "只输出 JSON。\n"
            "用户输入：" + user_input
        )
        try:
            data = self._chat_json(
                [{"role": "user", "content": prompt}], max_tokens=50
            )
            intent = (data or {}).get("intent", "commute")
            if intent not in ("commute", "general"):
                intent = "commute"
            return {"intent": intent, "source": self.source_name, "error": ""}
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek 意图识别失败，默认按通勤处理：%s", exc)
            return {"intent": "commute", "source": self.source_name, "error": str(exc)}


class MockLLMService(LLMService):
    """降级实现：不调用任何模型，返回空结果，交由规则层处理。"""

    source_name = "mock"

    def parse_commute(self, user_input: str, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"ok": False, "data": existing or {}, "source": "mock", "error": "未配置 DeepSeek"}

    def explain_recommendation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "text": "", "source": "mock", "error": "未配置 DeepSeek"}

    def chat_free_text(self, user_input: str) -> Dict[str, Any]:
        return {"ok": False, "text": "", "source": "mock", "error": "未配置 DeepSeek"}

    def classify_intent(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Mock 无法判断意图，默认按通勤处理（走原流程），避免测试行为漂移
        return {"intent": "commute", "source": "mock", "error": "未配置 DeepSeek"}


def build_llm_service() -> LLMService:
    """根据配置构建 LLM 服务（真实 or Mock）。

    同时检查环境变量与应用 settings（pydantic-settings 已加载 .env），
    两者取或，确保 .env 配置与实际进程环境变量均能生效。
    """
    from ..config import settings

    api_key = os.getenv("DEEPSEEK_API_KEY", "") or settings.deepseek_api_key
    if api_key:
        return DeepSeekLLMService(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "") or settings.deepseek_base_url,
            model=os.getenv("DEEPSEEK_MODEL", "") or settings.deepseek_model,
            timeout=settings.agent_request_timeout,
        )
    return MockLLMService()
