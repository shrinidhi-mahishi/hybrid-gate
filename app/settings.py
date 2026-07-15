"""HybridGate settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4o-mini"
    USE_LLM: bool = False
    DATA_DIR: str = "data"
    ENFORCE_HYBRID_GATE: bool = True
    PORT: int = 8000

    @property
    def has_llm_key(self) -> bool:
        if self.LLM_PROVIDER == "google":
            return bool(self.GOOGLE_API_KEY)
        return bool(self.OPENAI_API_KEY)

    @property
    def data_path(self) -> Path:
        p = Path(self.DATA_DIR)
        if not p.is_absolute():
            p = ROOT / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return self.data_path / "hybrid_gate.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
