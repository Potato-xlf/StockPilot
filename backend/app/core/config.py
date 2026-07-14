from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "StockPilot"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://stockpilot:stockpilot@localhost:5432/stockpilot"
    database_sync_url: str = "postgresql+psycopg://stockpilot:stockpilot@localhost:5432/stockpilot"
    redis_url: str | None = None
    market_timezone: str = "Asia/Shanghai"
    akshare_request_concurrency: int = 4
    akshare_request_retries: int = 3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
