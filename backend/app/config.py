from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-driven configuration (env prefix: PULSE_)."""

    app_name: str = "Pulse"
    # Default works with the docker-compose in this repo.
    database_url: str = "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse"
    echo_sql: bool = False
    auth_enabled: bool = False
    auth_secret: str = "dev-secret-change-me"
    check_concurrency: int = 8

    model_config = {"env_prefix": "PULSE_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
