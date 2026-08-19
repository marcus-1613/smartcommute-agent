"""应用配置：从环境变量读取，提供缺省值与启动校验。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。字段可通过环境变量（不区分大小写）覆盖。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # 数据库
    database_url: str = "sqlite:///./smartcommute.db"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 地图 / 路线
    onemap_token: str = ""
    onemap_routing_endpoint: str = (
        "https://www.onemap.gov.sg/api/public/routingsvc/route"
    )
    google_maps_api_key: str = ""
    google_maps_routes_endpoint: str = (
        "https://routes.googleapis.com/directions/v2:computeRoutes"
    )
    lta_account_key: str = ""
    lta_datamall_base_url: str = "https://datamall.lta.gov.sg"

    # 天气
    weather_api_key: str = ""
    weather_api_base_url: str = ""
    weather_provider: str = "open_meteo"  # open_meteo | mock

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Agent
    agent_max_retries: int = 2
    agent_request_timeout: float = 20.0

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def deepseek_enabled(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def google_maps_enabled(self) -> bool:
        return bool(self.google_maps_api_key)

    @property
    def onemap_enabled(self) -> bool:
        return bool(self.onemap_token)

    @property
    def lta_enabled(self) -> bool:
        return bool(self.lta_account_key)

    @property
    def weather_enabled(self) -> bool:
        return self.weather_provider != "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
