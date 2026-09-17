"""HTTP-shaped errors. Codes match the Jev-compatible taxonomy."""

from __future__ import annotations


class JevsorError(Exception):
    status = 500

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        if status is not None:
            self.status = status


class AuthError(JevsorError):
    status = 401


class ValidationError(JevsorError):
    status = 422


class RateLimitError(JevsorError):
    status = 429

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class OverloadedError(JevsorError):
    status = 529


class RefusalError(JevsorError):
    status = 422


class ProviderError(JevsorError):
    status = 502
