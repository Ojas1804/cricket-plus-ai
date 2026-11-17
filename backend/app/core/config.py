from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = ""
    redis_url: str = ""
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_model: str = ""
    cricket_data_provider: str = "mock"
    live_score_api_key: str = ""
    live_score_refresh_seconds: int = 60
    live_score_provider: str = "mock"
    live_poller: str = "embedded"
    analytics_cache_ttl_seconds: int = 600
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
