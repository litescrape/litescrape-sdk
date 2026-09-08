"""Public entry points: scrape / ascrape and key_status / akey_status."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import pydantic
from tqdm import tqdm

from . import _runtime
from .errors import (
    APIError,
    AuthenticationError,
    LitescrapeError,
    PaymentRequiredError,
    TransportError,
    ValidationError,
)
from .models import REQUEST_ADAPTER, REQUEST_TYPES, KeyStatus, ScrapeRequest, TimeoutSeconds

RequestItem = Mapping[str, Any] | ScrapeRequest
_FATAL_CODES = frozenset({"api_key_disabled"})
_TIMEOUT_ADAPTER = pydantic.TypeAdapter(TimeoutSeconds)


@dataclass(frozen=True, slots=True)
class Result:
    """Outcome of one request in a batch; ``index`` is its position in the input list."""

    index: int
    request: ScrapeRequest
    data: dict[str, Any] | None
    error: LitescrapeError | None
    status_code: int | None
    request_id: str
    attempts: int
    elapsed: float

    @property
    def ok(self) -> bool:
        return self.error is None

    def raise_for_error(self) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.data if self.data is not None else {}


class _Batch:
    __slots__ = ("fatal",)

    def __init__(self) -> None:
        self.fatal: APIError | None = None


def _describe(exc: pydantic.ValidationError) -> str:
    lines = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"] if part not in REQUEST_TYPES)
        message = error["msg"]
        if error["type"] == "union_tag_not_found":
            message += f" (valid endpoint values: {', '.join(sorted(REQUEST_TYPES))})"
        lines.append(f"{location}: {message}" if location else message)
    return "; ".join(lines)


def _validate(items: Sequence[RequestItem], request_timeout: float | None = None) -> list[ScrapeRequest]:
    validated: list[ScrapeRequest] = []
    problems: list[tuple[int, str]] = []
    for index, item in enumerate(items):
        try:
            request = REQUEST_ADAPTER.validate_python(item)
            if request.timeout is None and request_timeout is not None:
                request = request.model_copy(update={"timeout": request_timeout})
            validated.append(request)
        except pydantic.ValidationError as exc:
            problems.append((index, _describe(exc)))
    if problems:
        raise ValidationError(problems)
    return validated


def _check_args(attempts: int, concurrency: int | None, timeout: float) -> None:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if concurrency is not None and concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    if timeout <= 0:
        raise ValueError("timeout must be positive")


def _resolve_key(api_key: str | None) -> str:
    key = (api_key or os.environ.get("LITESCRAPE_API_KEY") or "").strip()
    if not key:
        raise AuthenticationError(
            "Pass api_key or set the LITESCRAPE_API_KEY environment variable.",
            status_code=None,
            error_code="missing_api_key",
        )
    return key


def _resolve_base_url(base_url: str | None) -> str:
    return (base_url or os.environ.get("LITESCRAPE_API_URL") or _runtime.DEFAULT_BASE_URL).rstrip("/")


async def _fetch_status(
    client: httpx.AsyncClient, headers: dict[str, str], attempts: int, timeout: float
) -> KeyStatus:
    outcome = await _runtime.request_with_retries(
        client, "/api/keys/status", {}, headers=headers, attempts=attempts, timeout=timeout
    )
    if outcome.error is not None:
        raise outcome.error
    try:
        return KeyStatus.model_validate({**(outcome.data or {}), "request_id": outcome.request_id})
    except pydantic.ValidationError as exc:
        raise TransportError(f"Unexpected key status body: {exc}", retryable=False, cause=exc) from exc


async def _run_one(
    client: httpx.AsyncClient,
    index: int,
    request: ScrapeRequest,
    headers: dict[str, str],
    attempts: int,
    timeout: float,
    semaphore: asyncio.Semaphore,
    batch: _Batch,
) -> Result:
    started = time.monotonic()
    try:
        outcome = await _runtime.request_with_retries(
            client,
            request.path,
            request.query_params(),
            headers=headers,
            attempts=attempts,
            timeout=timeout,
            semaphore=semaphore,
            gate=lambda: batch.fatal,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        outcome = _runtime.Outcome(
            error=TransportError(f"Unexpected {type(exc).__name__}: {exc}", retryable=False, cause=exc)
        )
    error = outcome.error
    if isinstance(error, APIError) and (error.status_code in (401, 402) or error.error_code in _FATAL_CODES):
        batch.fatal = error
    return Result(
        index=index,
        request=request,
        data=outcome.data,
        error=error,
        status_code=outcome.status_code,
        request_id=outcome.request_id,
        attempts=outcome.attempts,
        elapsed=time.monotonic() - started,
    )


async def ascrape(
    requests: Sequence[RequestItem],
    *,
    api_key: str | None = None,
    attempts: int = 5,
    concurrency: int | None = None,
    timeout: float = 120.0,
    request_timeout: float | None = None,
    tqdm_disable: bool = False,
    base_url: str | None = None,
) -> list[Result]:
    """Async form of :func:`scrape`: same arguments, results, and errors, run on the current event loop.

    ``scrape`` runs this coroutine on a private background loop so it can be called from anywhere,
    including inside a running loop; call ``ascrape`` directly from asyncio code.
    """
    _check_args(attempts, concurrency, timeout)
    if request_timeout is not None:
        try:
            request_timeout = _TIMEOUT_ADAPTER.validate_python(request_timeout)
        except pydantic.ValidationError as exc:
            raise ValueError("request_timeout must be a finite number greater than 0 and at most 90") from exc
    items = _validate(list(requests), request_timeout)
    if not items:
        return []
    key = _resolve_key(api_key)
    url = _resolve_base_url(base_url)
    headers = {"Authorization": f"Bearer {key}"}
    client = _runtime.client_for(url)
    status = await _fetch_status(client, headers, attempts, timeout)
    if status.remaining_calls < len(items):
        raise PaymentRequiredError(
            f"This batch needs {len(items)} calls but the key has {status.remaining_calls} remaining.",
            status_code=402,
            error_code="payment_required",
            request_id=status.request_id,
        )
    limit = _runtime.effective_limit(
        status.concurrency_limit,
        concurrency,
        selector_limited=_runtime.is_selector_limited(asyncio.get_running_loop()),
    )
    semaphore = _runtime.semaphore_for(key, url, limit)
    batch = _Batch()
    tasks = [
        asyncio.create_task(_run_one(client, index, item, headers, attempts, timeout, semaphore, batch))
        for index, item in enumerate(items)
    ]
    results: list[Result | None] = [None] * len(items)
    bar = tqdm(total=len(items), disable=tqdm_disable or len(items) == 1, unit="req")
    try:
        for completed in asyncio.as_completed(tasks):
            result = await completed
            results[result.index] = result
            bar.update(1)
    except BaseException:
        for task in tasks:
            task.cancel()
        raise
    finally:
        bar.close()
    return [result for result in results if result is not None]


def scrape(
    requests: Sequence[RequestItem],
    *,
    api_key: str | None = None,
    attempts: int = 5,
    concurrency: int | None = None,
    timeout: float = 120.0,
    request_timeout: float | None = None,
    tqdm_disable: bool = False,
    base_url: str | None = None,
) -> list[Result]:
    """Run every item in ``requests`` against the Litescrape API; one ``Result`` per item, in input order.

    Each item is a dict with an ``endpoint`` key, or a typed request object::

        from litescrape_sdk import GoogleMaps, GoogleSearch, scrape

        results = scrape([
            {"endpoint": "google_search", "q": "coffee grinders", "gl": "us"},
            GoogleMaps(q="coffee", type="search", ll="@40.745,-73.988,14z"),
        ])
        for result in results:
            if result.ok:
                print(result.data["search_metadata"]["id"])
            else:
                print(result.error)

    ``endpoint`` values are the slugs in ``REQUEST_TYPES`` (``google_search``, ``google_maps``,
    ``google_reviews``, ``bing_search``, ``yelp_reviews``, ...); each maps to a request class whose fields
    are that endpoint's query parameters and whose ``path`` is its route. Dicts are validated into the same
    classes, so both forms send identical requests. Unknown parameter names, wrong types, and missing
    required parameters are rejected locally.

    Before any request is sent:

    1. Every item is validated. If any item is invalid, ``ValidationError`` names each bad index and
       nothing is sent.
    2. The API key is resolved from ``api_key`` or the ``LITESCRAPE_API_KEY`` environment variable
       (``AuthenticationError`` if neither is set).
    3. ``GET /api/keys/status`` is fetched; it is not billed. ``PaymentRequiredError`` is raised if the key
       has fewer calls remaining than the batch needs. The status also supplies the key's concurrency limit.

    Requests run concurrently up to the key's ``concurrency_limit`` (25 when the key reports none), shared by
    every call in this process for the same key. ``concurrency`` can lower that cap, never raise it. On a
    Windows selector event loop the cap is also limited to 500. A progress bar advances as results arrive,
    in completion order; the returned list is always in input order. ``tqdm_disable=True`` hides the bar,
    and a single-item call shows none.

    Each item is tried up to ``attempts`` times (``attempts=1`` disables retries). Retried: connection
    errors and timeouts, HTTP 429 and 5xx, and any error the API marks ``retryable``. Not retried: 400,
    401, 402, 403, 404, 422. Waits grow exponentially with jitter from about 1 s, capped at 30 s, or follow
    the API's ``Retry-After``. Only a 200 response is billed; a retry is a new call, so if an attempt
    succeeded server-side but its response was lost in transit, both calls are billed.

    ``request_timeout`` sets the API's whole-request deadline in seconds for each attempt, from gateway
    receipt through admission, scraping, and billing. It must be finite, greater than 0, and at most 90.
    An item's ``timeout`` overrides this default. Omitting both preserves the API's standard deadline.
    Expiry returns HTTP 503 ``request_deadline_exceeded`` as ``RequestDeadlineExceededError``, with
    ``retryable=True`` and a request ID. That attempt is not charged, and the API cancels its underlying
    scrape. Credit/concurrency cleanup can finish shortly after the error response. Automatic retries
    each get a new deadline; use ``attempts=1`` to return after the first attempt. This does not cap SDK
    queueing, the status check, network transit, backoff, or the entire batch.

    ``timeout`` remains the HTTP transport timeout (120 seconds by default). Keep it longer than the
    server deadline to receive the API's response. A local transport timeout alone does not establish
    whether the server completed and billed a request.

    Per-item failures never raise. ``Result.ok`` is False and ``Result.error`` holds the exception: an
    ``APIError`` subclass with ``status_code``, ``error_code``, and ``request_id`` for API envelopes
    (``NotFoundError`` for a 404, for example Google AI Overview when no overview exists), or
    ``TransportError`` when no usable response arrived. ``Result.raise_for_error()`` raises it or returns
    ``Result.data``. A 401, 402, or disabled-key error seen mid-batch is copied to every item not yet
    started, without further requests.

    Ctrl-C (or cancelling the task) cancels in-flight requests; a request the API had already completed
    is still billed.

    Args:
        requests: dicts with an ``endpoint`` key, or request objects such as ``GoogleSearch(q=...)``.
        api_key: bearer key; defaults to ``LITESCRAPE_API_KEY``.
        attempts: total tries per item, at least 1.
        concurrency: optional lower cap on in-flight requests, at least 1.
        timeout: HTTP transport timeout in seconds per attempt (default 120).
        request_timeout: default server deadline in seconds per attempt; overridden by each item's timeout.
        tqdm_disable: hide the progress bar.
        base_url: API origin; defaults to ``LITESCRAPE_API_URL`` or ``https://api.litescrape.com``.

    Returns:
        ``list[Result]`` aligned with ``requests``.

    Raises:
        ValidationError, AuthenticationError, PaymentRequiredError, APIError, TransportError: before any
        scrape request is sent, as described above. ``ValueError`` for out-of-range arguments.
    """
    return _runtime.run_sync(
        ascrape(
            requests,
            api_key=api_key,
            attempts=attempts,
            concurrency=concurrency,
            timeout=timeout,
            request_timeout=request_timeout,
            tqdm_disable=tqdm_disable,
            base_url=base_url,
        )
    )


async def akey_status(api_key: str | None = None, *, base_url: str | None = None) -> KeyStatus:
    """Async form of :func:`key_status`."""
    key = _resolve_key(api_key)
    url = _resolve_base_url(base_url)
    client = _runtime.client_for(url)
    return await _fetch_status(client, {"Authorization": f"Bearer {key}"}, attempts=5, timeout=120.0)


def key_status(api_key: str | None = None, *, base_url: str | None = None) -> KeyStatus:
    """Read the key's balance and limits from ``GET /api/keys/status``; the call is not billed.

    Returns a ``KeyStatus`` with ``remaining_calls``, ``concurrency_limit``, ``status``, and the other
    fields the API reports. Raises ``AuthenticationError`` for a missing or invalid key.
    """
    return _runtime.run_sync(akey_status(api_key, base_url=base_url))
