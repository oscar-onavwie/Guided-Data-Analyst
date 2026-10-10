"""A single error type for problems the user can understand and act on.

The analysis modules raise `AppError`; the API layer turns it into a JSON
response with a stable `code`, a plain-English `message` and an HTTP status.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}
