from __future__ import annotations

import platform

import httpx

from litescrape_sdk import __version__, _runtime


def test_client_identifies_the_sdk_on_every_request() -> None:
    client = _runtime._make_client("https://api.test")
    try:
        user_agent = client.headers["user-agent"]
        assert user_agent.startswith(f"litescrape-sdk/{__version__} (")
        assert f"Python/{platform.python_version()}" in user_agent
        assert f"httpx/{httpx.__version__}" in user_agent
        assert client.headers["x-litescrape-client"] == f"python-sdk/{__version__}"
        assert client.headers["accept"] == "application/json"
    finally:
        _runtime.run_sync(client.aclose())


def test_per_request_headers_do_not_drop_the_identity() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(
        base_url="https://api.test",
        transport=httpx.MockTransport(handler),
        headers=_runtime._make_client("https://api.test").headers,
    )

    async def call() -> None:
        try:
            await _runtime.request_with_retries(
                client,
                "/api/google/search",
                {"q": "x"},
                headers={"Authorization": "Bearer k"},
                attempts=1,
                timeout=5,
            )
        finally:
            await client.aclose()

    _runtime.run_sync(call())
    (request,) = seen
    assert request.headers["user-agent"] == _runtime.USER_AGENT
    assert request.headers["x-litescrape-client"] == _runtime.CLIENT_HEADER_VALUE
    assert request.headers["authorization"] == "Bearer k"
