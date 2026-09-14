"""Event loop, HTTP client, concurrency gate, and retry loop behind the public functions."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import platform
import random
import sys
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx

from ._version import __version__
from .errors import APIError, LitescrapeError, TransportError, api_error_from_response

DEFAULT_BASE_URL = "https://api.litescrape.com"
DEFAULT_CONCURRENCY = 25
CLIENT_NAME = "litescrape-sdk"
# Every request identifies the SDK so the API can attribute usage to this
# channel: a product token first, then the runtime in a standard UA comment.
USER_AGENT = (
    f"{CLIENT_NAME}/{__version__} "
    f"(Python/{platform.python_version()}; httpx/{httpx.__version__}; {platform.system() or 'unknown'})"
)
CLIENT_HEADER = "X-Litescrape-Client"
CLIENT_HEADER_VALUE = f"python-sdk/{__version__}"
SELECTOR_LOOP_CAP = 500
BACKOFF_CAP = 30.0
CONNECT_TIMEOUT = 10.0

_RETRY_CODES = frozenset(
    {"proxy_capacity_unavailable", "upstream_session_unavailable", "service_unavailable"}
)
_RETRY_TRANSPORT = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)

T = TypeVar("T")
_LoopEntry = tuple[asyncio.AbstractEventLoop, dict[Any, Any]]

_clients: dict[int, _LoopEntry] = {}
_semaphores: dict[int, _LoopEntry] = {}
_sleep = asyncio.sleep


@dataclass(slots=True)
class Outcome:
    data: dict[str, Any] | None = None
    error: LitescrapeError | None = None
    status_code: int | None = None
    request_id: str = ""
    attempts: int = 0


def _per_loop(registry: dict[int, _LoopEntry]) -> dict[Any, Any]:
    loop = asyncio.get_running_loop()
    for key, (known, _) in list(registry.items()):
        if known.is_closed():
            del registry[key]
    return registry.setdefault(id(loop), (loop, {}))[1]


def _make_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            CLIENT_HEADER: CLIENT_HEADER_VALUE,
        },
        limits=httpx.Limits(max_connections=None, max_keepalive_connections=None),
        timeout=httpx.Timeout(120.0, connect=CONNECT_TIMEOUT),
    )


def client_for(base_url: str) -> httpx.AsyncClient:
    clients = _per_loop(_clients)
    client = clients.get(base_url)
    if client is None:
        client = clients[base_url] = _make_client(base_url)
    return client


def semaphore_for(api_key: str, base_url: str, limit: int) -> asyncio.Semaphore:
    semaphores = _per_loop(_semaphores)
    entry = semaphores.get((api_key, base_url))
    if entry is None or entry[0] != limit:
        entry = semaphores[(api_key, base_url)] = (limit, asyncio.Semaphore(limit))
    return entry[1]


def is_selector_limited(loop: asyncio.AbstractEventLoop) -> bool:
    return sys.platform == "win32" and isinstance(loop, asyncio.SelectorEventLoop)


def effective_limit(status_limit: int | None, override: int | None, *, selector_limited: bool) -> int:
    limit = status_limit or DEFAULT_CONCURRENCY
    if override is not None:
        limit = min(limit, override)
    if selector_limited:
        limit = min(limit, SELECTOR_LOOP_CAP)
    return max(1, limit)


def _should_retry(error: LitescrapeError) -> bool:
    if isinstance(error, TransportError):
        return error.retryable
    if isinstance(error, APIError):
        status = error.status_code or 0
        return error.retryable or status == 429 or status >= 500 or error.error_code in _RETRY_CODES
    return False


def _delay(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(max(retry_after, 0.0), BACKOFF_CAP)
    ceiling = min(BACKOFF_CAP, float(2 ** min(max(attempt - 1, 0), 6)))
    return random.uniform(ceiling / 2, ceiling)


async def _attempt(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, str],
    headers: dict[str, str],
    timeout: float,
    outcome: Outcome,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    accepted_statuses: tuple[int, ...] = (200,),
) -> LitescrapeError | None:
    outcome.status_code, outcome.request_id = None, ""
    try:
        response = await client.request(
            method,
            path,
            params=params,
            **({"json": json_body} if json_body is not None else {}),
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=min(CONNECT_TIMEOUT, timeout)),
        )
    except _RETRY_TRANSPORT as exc:
        return TransportError(f"{type(exc).__name__}: {exc}", retryable=True, cause=exc)
    except Exception as exc:
        return TransportError(f"{type(exc).__name__}: {exc}", retryable=False, cause=exc)
    outcome.status_code = response.status_code
    outcome.request_id = response.headers.get("x-request-id", "")
    if response.status_code not in accepted_statuses:
        error = api_error_from_response(response)
        outcome.request_id = error.request_id or outcome.request_id
        return error
    try:
        data = response.json()
    except ValueError as exc:
        return TransportError("Response body was not JSON", retryable=True, cause=exc)
    if not isinstance(data, dict):
        return TransportError("Response body was not a JSON object", retryable=True)
    outcome.data = data
    return None


async def request_with_retries(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, str],
    *,
    headers: dict[str, str],
    attempts: int,
    timeout: float,
    semaphore: asyncio.Semaphore | None = None,
    gate: Callable[[], LitescrapeError | None] | None = None,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    accepted_statuses: tuple[int, ...] = (200,),
) -> Outcome:
    outcome = Outcome()
    slot = semaphore if semaphore is not None else contextlib.nullcontext()
    for attempt in range(1, attempts + 1):
        async with slot:
            blocked = gate() if gate is not None else None
            if blocked is not None:
                outcome.error = blocked
                outcome.status_code = getattr(blocked, "status_code", None)
                return outcome
            outcome.attempts = attempt
            error = await _attempt(
                client,
                path,
                params,
                headers,
                timeout,
                outcome,
                method=method,
                json_body=json_body,
                accepted_statuses=accepted_statuses,
            )
        outcome.error = error
        if error is None:
            return outcome
        if attempt == attempts or not _should_retry(error):
            return outcome
        await _sleep(_delay(attempt, getattr(error, "retry_after", None)))
    return outcome


_loop_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def background_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, name="litescrape-sdk", daemon=True).start()
            _loop = loop
        return _loop


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    future = asyncio.run_coroutine_threadsafe(coro, background_loop())
    try:
        while True:
            try:
                return future.result(timeout=0.25)
            except concurrent.futures.TimeoutError:
                continue
    except BaseException:
        future.cancel()
        raise
