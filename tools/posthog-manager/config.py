"""config.py — PostHog manager configuration using pydantic-settings v2."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PostHog credentials, sourced from .env at the toolbelt repo root."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    posthog_api_key: str = ""
    posthog_project_id: int | None = None
    posthog_host: str = "https://us.posthog.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
