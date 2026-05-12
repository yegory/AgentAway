from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/pocket_maintainer"
    redis_url: str = "redis://redis:6379/0"
    github_webhook_secret: str = ""
    github_app_id: str = ""
    github_app_private_key_base64: str = ""
    github_app_client_id: str = ""
    github_app_client_secret: str = ""
    github_app_slug: str = ""
    app_encryption_key: str = ""
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_authorized_parties: str = ""
    app_access_token_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    api_rate_limit_per_minute: int = 60
    default_openai_model: str = "gpt-4.1-mini"
    default_anthropic_model: str = "claude-sonnet-4-5"
    default_deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    agentaway_dev_user_id: str = "dev-user"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def cors_origins() -> list[str]:
    origins = [settings.web_base_url]
    if settings.app_env != "production":
        origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])
    return list(dict.fromkeys(origin for origin in origins if origin))


def validate_production_settings() -> None:
    if settings.app_env != "production":
        return

    required = {
        "APP_ENCRYPTION_KEY": settings.app_encryption_key,
        "APP_ACCESS_TOKEN_SECRET": settings.app_access_token_secret,
        "GITHUB_WEBHOOK_SECRET": settings.github_webhook_secret,
        "CLERK_ISSUER or CLERK_JWKS_URL": settings.clerk_issuer or settings.clerk_jwks_url,
    }
    missing = [name for name, value in required.items() if not str(value).strip()]
    if missing:
        raise RuntimeError(f"Missing production security settings: {', '.join(missing)}")
