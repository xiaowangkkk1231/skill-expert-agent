from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SEA_", env_file=str(BASE_DIR / ".env"), extra="ignore"
    )

    provider: str = "auto"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "anthropic/claude-3.5-haiku"
    max_input_chars: int = 60_000
    stream_pace_ms: int = 0
    db_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'sea.db').as_posix()}"

    @property
    def resolved_provider(self) -> str:
        """auto 模式下按是否配了 key 决定走模型还是走规则引擎。"""
        if self.provider == "llm":
            return "llm" if self.llm_api_key else "rule"
        if self.provider == "rule":
            return "rule"
        return "llm" if self.llm_api_key else "rule"


@lru_cache
def get_settings() -> Settings:
    return Settings()
