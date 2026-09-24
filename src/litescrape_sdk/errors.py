"""Exceptions raised by litescrape_sdk."""

from __future__ import annotations

import email.utils
import time
from typing import Any

import httpx


class LitescrapeError(Exception):
    """Base class for every error raised by this package."""


class ValidationError(LitescrapeError, ValueError):
    """One or more request items failed validation; nothing was sent."""

    def __init__(self, problems: list[tuple[int, str]]) -> None:
        self.problems = problems
        summary = "\n".join(f"  [{index}] {message}" for index, message in problems)
        super().__init__(f"{len(problems)} invalid request item(s):\n{summary}")


class TransportError(LitescrapeError):
    """No usable HTTP response: connection failure, timeout, or an unreadable body."""

    def __init__(self, message: str, *, retryable: bool, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.cause = cause


class APIError(LitescrapeError):
    """The API answered with an error envelope."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None,
        error_code: str,
        request_id: str = "",
        retryable: bool = False,
        body: dict[str, Any] | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id
        self.retryable = retryable
        self.body = body if body is not None else {}
        self.retry_after = retry_after

    def __str__(self) -> str:
        details = [self.error_code]
        if self.status_code is not None:
            details.append(f"HTTP {self.status_code}")
        if self.request_id:
            details.append(f"request {self.request_id}")
        return f"{self.message} ({', '.join(details)})"


class AuthenticationError(APIError):
    """401, or no API key was available."""


class PaymentRequiredError(APIError):
    """402, or the key has fewer calls than the batch needs."""


class NotFoundError(APIError):
    """404: the resource does not exist."""


class RateLimitError(APIError):
    """429: the key's concurrency or request limit was reached."""


class RequestDeadlineExceededError(APIError):
    """The API's whole-request deadline expired; this attempt is retryable and is not charged."""


_BY_STATUS: dict[int, type[APIError]] = {
    401: AuthenticationError,
    402: PaymentRequiredError,
    404: NotFoundError,
    429: RateLimitError,
}


def api_error_from_response(response: httpx.Response) -> APIError:
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or "error_code" not in body:
        detail = body.get("detail") if isinstance(body, dict) else None
        body = {
            "error": str(detail) if detail else f"HTTP {status}",
            "error_code": "not_found" if status == 404 else "request_failed",
            "status_code": status,
            "request_id": response.headers.get("x-request-id", ""),
            "retryable": status == 429 or status >= 500,
        }
    cls = (
        RequestDeadlineExceededError
        if status == 503 and body["error_code"] == "request_deadline_exceeded"
        else _BY_STATUS.get(status, APIError)
    )
    return cls(
        str(body.get("error") or f"HTTP {status}"),
        status_code=status,
        error_code=str(body["error_code"]),
        request_id=str(body.get("request_id") or response.headers.get("x-request-id", "")),
        retryable=body.get("retryable") is True,
        body=body,
        retry_after=parse_retry_after(response.headers.get("retry-after")),
    )


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - time.time())
