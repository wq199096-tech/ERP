from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
