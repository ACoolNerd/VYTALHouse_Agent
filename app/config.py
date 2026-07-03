from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VYTAL_",
        extra="ignore",
    )

    app_name: str = "VYTALHouse Agent Platform"
    environment: str = "development"
    database_url: str = "sqlite:///./data/vytalhouse.db"
    admin_token: str = "local-admin-token-change-me"
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    embedded_worker: bool = True
    worker_poll_seconds: float = 0.2
    max_task_retries: int = 2
    log_level: str = "INFO"
    knowledge_dir: str = "knowledge/seed"

    @property
    def knowledge_path(self) -> Path:
        return Path(self.knowledge_dir)


def build_settings(overrides: dict | None = None) -> Settings:
    if not overrides:
        return Settings()
    base = Settings().model_dump()
    base.update(overrides)
    return Settings.model_validate(base)
