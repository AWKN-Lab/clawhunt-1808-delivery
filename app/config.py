"""Runtime configuration read from environment variables.

Local default is SQLite + mock LLM + in-process KB retrieval. PostgreSQL /
Redis / OpenAI-compatible DeepSeek are opt-in through env vars.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    db_mode: str = "sqlite"
    database_url: str = ""
    sqlite_path: str = ""
    llm_mode: str = "mock"
    llm_fault: str = "none"  # none | timeout | error
    llm_timeout_s: float = 2.0
    openai_base_url: str = "https://api.deepseek.com/v1"
    openai_api_key: str = ""
    openai_model: str = "deepseek-chat"
    audit_dir: str = ""
    kb_dir: str = ""
    outbox_secret: str = "local-dev-outbox-secret"
    redis_url: str = ""
    stream_delay_ms: int = 5

    def __post_init__(self) -> None:
        if not self.sqlite_path:
            self.sqlite_path = str(ROOT / "data" / "agent.db")
        if not self.audit_dir:
            self.audit_dir = str(ROOT / "audit")
        if not self.kb_dir:
            self.kb_dir = str(ROOT / "kb" / "docs")

    @property
    def dsn(self) -> str:
        if self.database_url:
            return self.database_url
        if self.db_mode == "postgres":
            return (
                "postgresql+asyncpg://agent:agent@127.0.0.1:5432/agent"
            )
        return f"sqlite+aiosqlite:///{Path(self.sqlite_path).as_posix()}"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_mode=_env("DB_MODE", "sqlite"),
            database_url=_env("DATABASE_URL"),
            sqlite_path=_env("SQLITE_PATH"),
            llm_mode=_env("LLM_MODE", "mock"),
            llm_fault=_env("LLM_FAULT", "none"),
            llm_timeout_s=float(_env("LLM_TIMEOUT_S", "2.0")),
            openai_base_url=_env("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
            openai_api_key=_env("OPENAI_API_KEY"),
            openai_model=_env("OPENAI_MODEL", "deepseek-chat"),
            audit_dir=_env("AUDIT_DIR"),
            kb_dir=_env("KB_DIR"),
            outbox_secret=_env("OUTBOX_HMAC_SECRET", "local-dev-outbox-secret"),
            redis_url=_env("REDIS_URL"),
            stream_delay_ms=int(_env("STREAM_DELAY_MS", "5")),
        )
