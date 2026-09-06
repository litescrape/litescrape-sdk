from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from litescrape_sdk import _runtime

BASE_URL = "https://api.test"
STATUS_PATH = "/api/keys/status"
DEFAULT_STATUS = {
    "remaining_calls": 1000,
    "free_calls": 10,
    "minimum_top_up_cents": 1000,
    "cents_per_1000_calls": 15,
    "status": "active",
    "has_billing_email": False,
    "concurrency_limit": 25,
    "credit_expiry_months": 6,
    "credits_expire_at": None,
    "expiring_calls": None,
}


def envelope(status: int, error_code: str, *, retryable: bool = False, headers: dict | None = None):
    body = {
        "error": f"{error_code} happened",
        "error_code": error_code,
        "status_code": status,
        "request_id": "abc123",
        "retryable": retryable,
    }
    return httpx.Response(status, json=body, headers={"x-request-id": "abc123", **(headers or {})})


def success(request: httpx.Request) -> httpx.Response:
    body = {"search_metadata": {"id": "ok"}, "search_parameters": dict(request.url.params)}
    return httpx.Response(200, json=body, headers={"x-request-id": "req-ok"})


class MockApi:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.status: dict[str, Any] = dict(DEFAULT_STATUS)
        self.queues: dict[str, list[Any]] = {}
        self.default: Callable[[httpx.Request], Any] = success
        self.sleeps: list[float] = []
        self.delay = 0.0
        self.in_flight = 0
        self.peak = 0
        self.completed: list[str] = []
        self.clients_made = 0
        self.status_override: Any = None

    def queue(self, path: str, *items: Any) -> None:
        self.queues.setdefault(path, []).extend(items)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path == STATUS_PATH:
            if self.status_override is not None:
                return self.status_override
            return httpx.Response(200, json=self.status, headers={"x-request-id": "status-id"})
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            queued = self.queues.get(path)
            item = queued.pop(0) if queued else self.default
            if isinstance(item, BaseException):
                raise item
            if callable(item):
                item = item(request)
                if inspect.isawaitable(item):
                    item = await item
            return item
        finally:
            self.in_flight -= 1
            self.completed.append(request.url.params.get("q", path))

    @property
    def scrape_calls(self) -> list[httpx.Request]:
        return [call for call in self.calls if call.url.path != STATUS_PATH]

    @property
    def status_calls(self) -> list[httpx.Request]:
        return [call for call in self.calls if call.url.path == STATUS_PATH]


@pytest.fixture
def mock_api(monkeypatch: pytest.MonkeyPatch) -> MockApi:
    api = MockApi()
    transport = httpx.MockTransport(api.handle)

    def make_client(base_url: str) -> httpx.AsyncClient:
        api.clients_made += 1
        return httpx.AsyncClient(base_url=base_url, transport=transport)

    async def fake_sleep(delay: float) -> None:
        api.sleeps.append(delay)

    _runtime._clients.clear()
    _runtime._semaphores.clear()
    monkeypatch.setattr(_runtime, "_make_client", make_client)
    monkeypatch.setattr(_runtime, "_sleep", fake_sleep)
    monkeypatch.setenv("LITESCRAPE_API_KEY", "ls_live_test_key")
    monkeypatch.setenv("LITESCRAPE_API_URL", BASE_URL)
    yield api
    _runtime._clients.clear()
    _runtime._semaphores.clear()
