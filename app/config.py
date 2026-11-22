"""Application settings, read from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://appuser:apppassword@localhost:5432/secure_users"
    bcrypt_rounds: int = 12

    # Signing key for login tokens (JWT, HS256). The default is for local
    # development only: set JWT_SECRET_KEY to a long random value in production.
    jwt_secret_key: str = "dev-only-change-me-please-use-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
