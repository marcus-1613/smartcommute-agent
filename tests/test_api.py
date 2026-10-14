"""后端 API 接口测试。"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# 确保 MCP 子进程使用 venv 的 Python
os.environ.setdefault(
    "SMARTCOMMUTE_PYTHON",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".venv", "Scripts", "python.exe")),
)


@pytest.fixture(scope="module")
def client():
    from app.main import app
    from app.models.database import init_db

    init_db()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_full_commute(client):
    r = client.post(
        "/api/chat",
        json={"message": "我明天早上8点从裕廊东去滨海湾，希望尽量少换乘"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"]
    assert data["reply"]
    assert len(data["route_scores"]) >= 1
    assert data["selected_route"] is not None


def test_chat_clarification(client):
    r = client.post("/api/chat", json={"message": "我想去滨海湾"})
    assert r.status_code == 200
    data = r.json()
    assert data["needs_clarification"] is True


def test_sessions_list_and_detail(client):
    r = client.get("/api/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert isinstance(sessions, list)
    if sessions:
        sid = sessions[0]["session_id"]
        d = client.get(f"/api/sessions/{sid}")
        assert d.status_code == 200
        assert "messages" in d.json()


def test_commutes_list(client):
    r = client.get("/api/commutes")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_preferences_get_and_update(client):
    r = client.get("/api/preferences")
    assert r.status_code == 200
    assert r.json()["default_mode"] == "transit"

    r2 = client.put(
        "/api/preferences",
        json={"prefer_fewer_transfers": 0.9, "max_walk_m": 600},
    )
    assert r2.status_code == 200
    assert r2.json()["prefer_fewer_transfers"] == 0.9
    assert r2.json()["max_walk_m"] == 600


def test_commute_detail_not_found(client):
    r = client.get("/api/commutes/999999")
    assert r.status_code == 404
