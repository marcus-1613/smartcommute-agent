"""LLM 服务测试：Mock/真实切换、缺 Key 处理、解析与解释降级。"""
from __future__ import annotations

import os

import pytest

from app.services.llm_service import (
    DeepSeekLLMService,
    MockLLMService,
    build_llm_service,
)


def test_build_llm_mock_when_no_key(monkeypatch):
    """缺少 API Key 时应构建 Mock 服务。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "")
    svc = build_llm_service()
    assert isinstance(svc, MockLLMService)
    assert svc.source_name == "mock"


def test_build_llm_real_when_key_present(monkeypatch):
    """存在 API Key 时应构建 DeepSeek 服务。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-123")
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-123")
    svc = build_llm_service()
    assert isinstance(svc, DeepSeekLLMService)
    assert svc.source_name == "deepseek"


def test_mock_parse_returns_not_ok():
    """Mock 服务 parse 返回 ok=False，交由规则层处理。"""
    svc = MockLLMService()
    r = svc.parse_commute("我明天8点从裕廊东去滨海湾")
    assert r["ok"] is False
    assert r["source"] == "mock"


def test_mock_explain_returns_not_ok():
    svc = MockLLMService()
    r = svc.explain_recommendation({})
    assert r["ok"] is False


def test_deepseek_parse_graceful_failure(monkeypatch):
    """DeepSeek 调用失败时应返回 ok=False，不抛异常。"""
    svc = DeepSeekLLMService(api_key="invalid-key", base_url="http://127.0.0.1:1", timeout=1.0)
    # 指向不可达地址，必然失败
    r = svc.parse_commute("我明天8点从裕廊东去滨海湾")
    assert r["ok"] is False
    assert r["source"] == "mock"  # 降级标记


def test_deepseek_explain_graceful_failure(monkeypatch):
    svc = DeepSeekLLMService(api_key="invalid-key", base_url="http://127.0.0.1:1", timeout=1.0)
    r = svc.explain_recommendation({"top_route": {}})
    assert r["ok"] is False


def test_mock_chat_free_text_returns_not_ok():
    svc = MockLLMService()
    r = svc.chat_free_text("什么是 LangGraph？")
    assert r["ok"] is False
    assert r["source"] == "mock"


def test_mock_classify_intent_defaults_commute():
    svc = MockLLMService()
    r = svc.classify_intent("你好")
    assert r["intent"] == "commute"


def test_deepseek_chat_free_text_graceful_failure():
    svc = DeepSeekLLMService(api_key="invalid-key", base_url="http://127.0.0.1:1", timeout=1.0)
    r = svc.chat_free_text("什么是 LangGraph？")
    assert r["ok"] is False
    assert r["text"] == ""


def test_deepseek_classify_intent_graceful_failure():
    svc = DeepSeekLLMService(api_key="invalid-key", base_url="http://127.0.0.1:1", timeout=1.0)
    r = svc.classify_intent("你好")
    assert r["intent"] == "commute"  # 失败默认走通勤，不阻断
