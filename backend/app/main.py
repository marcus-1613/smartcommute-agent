"""FastAPI 主应用入口。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import chat, commutes, preferences, sessions
from .config import settings
from .models.database import init_db

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if not settings.deepseek_enabled:
        logging.warning(
            "未配置 DEEPSEEK_API_KEY，Agent 将使用规则解析（不影响 Mock 演示）"
        )
    if not settings.google_maps_enabled:
        logging.info("未配置 GOOGLE_MAPS_API_KEY，路线将使用 Mock 数据")
    yield
    # 关闭 Checkpointer 连接，保证优雅退出
    await chat.shutdown_agent()


app = FastAPI(
    title="SmartCommute AI",
    description="智慧通勤 Agent 后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["health"])
def health():
    """健康检查。"""
    return {
        "status": "ok",
        "app": "SmartCommute AI",
        "mock_mode": not (settings.google_maps_enabled or settings.weather_enabled),
        "deepseek_enabled": settings.deepseek_enabled,
    }


app.include_router(chat.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(commutes.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
