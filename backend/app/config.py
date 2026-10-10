"""Application settings, read once from environment variables.

Every limit lives here so it is documented in one place and can be tuned
without touching the analysis code. See `.env.example` at the repo root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:  # fail loudly on a bad config rather than guess
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"Environment variable {name} must be positive, got {value}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Upload limits
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 20))
    max_rows: int = field(default_factory=lambda: _int("MAX_ROWS", 200_000))
    max_columns: int = field(default_factory=lambda: _int("MAX_COLUMNS", 200))
    max_cells: int = field(default_factory=lambda: _int("MAX_CELLS", 5_000_000))

    # In-memory session store
    session_ttl_minutes: int = field(default_factory=lambda: _int("SESSION_TTL_MINUTES", 30))
    max_sessions: int = field(default_factory=lambda: _int("MAX_SESSIONS", 20))

    # CORS: comma-separated list of allowed frontend origins
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
        )
    )

    # Optional AI explanations (off unless a key is configured AND AI_ENABLED=true)
    ai_enabled: bool = field(default_factory=lambda: _bool("AI_ENABLED", False))
    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or None)
    ai_model: str = field(default_factory=lambda: os.getenv("AI_MODEL", "claude-sonnet-5-5"))
    ai_timeout_seconds: int = field(default_factory=lambda: _int("AI_TIMEOUT_SECONDS", 60))

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def ai_available(self) -> bool:
        return self.ai_enabled and bool(self.anthropic_api_key)


def get_settings() -> Settings:
    return Settings()
