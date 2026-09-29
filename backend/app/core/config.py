"""Centralized application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the backend foundation."""

    app_name: str = "CityResponder Backend"
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8010
    database_url: str = "sqlite:///./data/cityresponder.db"
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    jwt_secret_key: str = "development-only-change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    dev_seed_password: str = "CityResponderDev123!"
    dev_operator_email: str = "operator@example.com"
    dev_firefighter_email: str = "firefighter@example.com"
    dev_risk_planner_email: str = "risk-planner@example.com"
    dev_admin_email: str = "admin@example.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""

    return Settings()
