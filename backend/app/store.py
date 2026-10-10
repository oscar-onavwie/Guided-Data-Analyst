"""In-memory dataset sessions.

Data retention (also stated in the UI and README):

* Uploaded files are parsed in memory and never written to disk.
* The parsed dataset is held in this process's memory for SESSION_TTL_MINUTES
  after it was last used (default 30), or until the user removes it, or until
  the server restarts — whichever comes first.
* At most MAX_SESSIONS datasets are held; the least recently used is evicted.
* Raw values are never written to logs.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import Settings
from .errors import AppError
from .inference import TypedTable
from .parsing import ParsedTable


@dataclass
class Session:
    dataset_id: str
    parsed: ParsedTable
    table: TypedTable
    loaded_at: datetime
    last_used: datetime
    is_demo: bool = False
    demo_key: str | None = None
    cache: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _ttl(self) -> timedelta:
        return timedelta(minutes=self.settings.session_ttl_minutes)

    def expires_at(self, session: Session) -> datetime:
        return session.last_used + self._ttl()

    def _purge_expired(self) -> None:
        now = self._now()
        for key in [k for k, s in self._sessions.items() if now > self.expires_at(s)]:
            del self._sessions[key]

    def add(self, parsed: ParsedTable, table: TypedTable, is_demo: bool = False, demo_key: str | None = None) -> Session:
        with self._lock:
            self._purge_expired()
            while len(self._sessions) >= self.settings.max_sessions:
                oldest = min(self._sessions.values(), key=lambda s: s.last_used)
                del self._sessions[oldest.dataset_id]
            now = self._now()
            # 128-bit random, URL-safe: not guessable, and never derived from the filename
            session = Session(
                dataset_id=secrets.token_urlsafe(16),
                parsed=parsed,
                table=table,
                loaded_at=now,
                last_used=now,
                is_demo=is_demo,
                demo_key=demo_key,
            )
            self._sessions[session.dataset_id] = session
            return session

    def get(self, dataset_id: str) -> Session:
        with self._lock:
            self._purge_expired()
            session = self._sessions.get(dataset_id)
            if session is None:
                raise AppError(
                    404,
                    "dataset_not_found",
                    "This dataset is no longer available. Datasets are kept in memory for a limited time; please upload it again.",
                )
            session.last_used = self._now()
            return session

    def delete(self, dataset_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(dataset_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)
