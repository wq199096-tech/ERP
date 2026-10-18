from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    enable_demo_data: bool = True
    database_url: str = "sqlite:///./smartorder-dev.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-change-this-secret"
    credential_encryption_key: str = ""
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    max_import_bytes: int = 10 * 1024 * 1024
    max_import_rows: int = 10_000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.is_production:
            if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("development-"):
                raise ValueError("生产环境必须提供至少 32 字符的强随机 JWT_SECRET")
            if not self.credential_encryption_key:
                raise ValueError("生产环境必须提供 CREDENTIAL_ENCRYPTION_KEY")
            try:
                Fernet(self.credential_encryption_key.encode())
            except (ValueError, TypeError) as exc:
                raise ValueError("CREDENTIAL_ENCRYPTION_KEY 必须是有效的 Fernet 密钥") from exc
            if self.enable_demo_data:
                raise ValueError("生产环境禁止启用 ENABLE_DEMO_DATA")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
