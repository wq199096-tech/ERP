from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    print_agent_token: str = "replace-with-local-agent-token"
    print_agent_db: str = "services/print-agent/data/print-agent.sqlite3"
    print_agent_output: str = "services/print-agent/output"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_path(self) -> Path:
        return Path(self.print_agent_db).resolve()

    @property
    def output_path(self) -> Path:
        return Path(self.print_agent_output).resolve()

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @model_validator(mode="after")
    def validate_token(self) -> "Settings":
        if self.is_production and (
            len(self.print_agent_token) < 32 or self.print_agent_token.startswith("replace-")
        ):
            raise ValueError("生产环境必须提供至少 32 字符的随机 PRINT_AGENT_TOKEN")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
