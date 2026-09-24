from __future__ import annotations

import asyncio
import sys
import threading
import time

import httpx
import pytest

from litescrape_sdk import (
    APIError,
    AuthenticationError,
    GoogleAiOverview,
    GoogleSearch,
    NotFoundError,
    PaymentRequiredError,
    RateLimitError,
    TransportError,
    ValidationError,
    _runtime,
    ascrape,
    key_status,
    scrape,
)
from tests.conftest import STATUS_PATH, envelope, success

SEARCH = "/api/google/search"
AI_OVERVIEW = "/api/google/ai-overview"


def item(index: int = 0) -> dict:
    return {"endpoint": "google_search", "q": f"q{index}"}


def items(count: int) -> list[dict]:
    return [item(index) for index in range(count)]


def run_async(*args, **kwargs):
    return asyncio.run(ascrape(*args, **kwargs))


@pytest.fixture(params=["sync", "async"])
def runner(request):
    return scrape if request.param == "sync" else run_async


def test_validation_rejects_whole_batch_before_http(mock_api, runner):
    with pytest.raises(ValidationError) as info:
        runner([item(), {"endpoint": "google_search", "bogus": 1}, {"q": "x"}])
    message = str(info.value)
    assert "[1]" in message and "bogus" in message
    assert "[2]" in message and "google_search" in message
    assert "[0]" not in message
    assert info.value.problems[0][0] == 1
    assert mock_api.calls == []


def test_dict_and_typed_inputs_send_identical_requests(mock_api, runner):
    results = runner([{"endpoint": "google_search", "q": "x", "gl": "us"}, GoogleSearch(q="x", gl="us")])
    first, second = mock_api.scrape_calls
    assert first.url == second.url
    assert first.url.path == SEARCH and dict(first.url.params) == {"q": "x", "gl": "us"}
    assert first.headers["authorization"] == "Bearer ls_live_test_key"
    assert [result.ok for result in results] == [True, True]


def test_results_keep_input_order(mock_api, runner):
    async def slow_first(request):
        if request.url.params["q"] == "q0":
            await asyncio.sleep(0.05)
        return success(request)

    mock_api.default = slow_first
    results = runner(items(3))
    assert [result.index for result in results] == [0, 1, 2]
    assert [result.request.q for result in results] == ["q0", "q1", "q2"]
    assert mock_api.completed[-1] == "q0"


@pytest.mark.parametrize(
    "failure",
    [
        envelope(503, "service_unavailable", retryable=True),
        envelope(429, "concurrency_limit_exceeded", retryable=False),
        envelope(500, "internal_error"),
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("slow"),
        httpx.RemoteProtocolError("closed"),
        httpx.Response(502, text="<html>bad gateway</html>"),
        httpx.Response(200, text="not json"),
    ],
)
def test_retries_then_succeeds(mock_api, runner, failure):
    mock_api.queue(SEARCH, failure, failure, success)
    (result,) = runner([item()])
    assert result.ok and result.attempts == 3
    assert len(mock_api.scrape_calls) == 3
    assert len(mock_api.sleeps) == 2


@pytest.mark.parametrize(
    "status, code, cls",
    [
        (400, "invalid_request", APIError),
        (401, "invalid_api_key", AuthenticationError),
        (402, "payment_required", PaymentRequiredError),
        (403, "forbidden", APIError),
        (404, "not_found", NotFoundError),
        (422, "validation_error", APIError),
    ],
)
def test_terminal_statuses_are_not_retried(mock_api, runner, status, code, cls):
    mock_api.queue(SEARCH, envelope(status, code), success)
    (result,) = runner([item()])
    assert not result.ok and result.attempts == 1
    assert isinstance(result.error, cls)
    assert result.error.status_code == status and result.error.error_code == code
    assert result.status_code == status and result.request_id == "abc123"
    assert len(mock_api.scrape_calls) == 1 and mock_api.sleeps == []


def test_unsupported_protocol_is_terminal(mock_api, runner):
    mock_api.queue(SEARCH, httpx.UnsupportedProtocol("nope"), success)
    (result,) = runner([item()])
    assert isinstance(result.error, TransportError) and not result.error.retryable
    assert result.attempts == 1 and mock_api.sleeps == []


def test_retry_after_is_honored_and_capped(mock_api, runner):
    mock_api.queue(
        SEARCH,
        envelope(503, "service_unavailable", retryable=True, headers={"retry-after": "10"}),
        envelope(503, "service_unavailable", retryable=True, headers={"retry-after": "99"}),
        success,
    )
    (result,) = runner([item()])
    assert result.ok and mock_api.sleeps == [10.0, 30.0]


def test_backoff_grows_with_jitter(mock_api, runner):
    mock_api.queue(SEARCH, *[envelope(503, "service_unavailable", retryable=True)] * 4, success)
    (result,) = runner([item()])
    assert result.ok and result.attempts == 5
    for attempt, delay in enumerate(mock_api.sleeps, start=1):
        ceiling = min(30.0, 2.0 ** (attempt - 1))
        assert ceiling / 2 <= delay <= ceiling


def test_attempts_exhausted_returns_retryable_error(mock_api, runner):
    mock_api.queue(SEARCH, *[envelope(503, "service_unavailable", retryable=True)] * 3, success)
    (result,) = runner([item()], attempts=3)
    assert not result.ok and result.attempts == 3
    assert isinstance(result.error, APIError) and result.error.retryable
    assert result.status_code == 503 and len(mock_api.sleeps) == 2


def test_attempts_one_disables_retries(mock_api, runner):
    mock_api.queue(SEARCH, envelope(429, "rate_limited"), success)
    (result,) = runner([item()], attempts=1)
    assert isinstance(result.error, RateLimitError) and result.attempts == 1
    assert mock_api.sleeps == []


def test_status_is_fetched_once_per_call_before_any_request(mock_api):
    for _ in range(5):
        scrape([item()])
    paths = [call.url.path for call in mock_api.calls]
    assert paths == [STATUS_PATH, SEARCH] * 5
    assert mock_api.status_calls[0].headers["authorization"] == "Bearer ls_live_test_key"


def test_balance_below_batch_size_raises_before_any_request(mock_api, runner):
    mock_api.status["remaining_calls"] = 2
    with pytest.raises(PaymentRequiredError) as info:
        runner(items(3))
    assert "3" in str(info.value) and "2" in str(info.value)
    assert info.value.error_code == "payment_required" and info.value.request_id == "status-id"
    assert mock_api.scrape_calls == [] and len(mock_api.status_calls) == 1


def test_balance_equal_to_batch_size_runs(mock_api, runner):
    mock_api.status["remaining_calls"] = 3
    assert all(result.ok for result in runner(items(3)))


def test_status_errors_raise(mock_api, runner):
    mock_api.status_override = envelope(401, "invalid_api_key")
    with pytest.raises(AuthenticationError) as info:
        runner([item()])
    assert info.value.error_code == "invalid_api_key"
    assert mock_api.scrape_calls == [] and len(mock_api.status_calls) == 1


def test_concurrency_follows_status_limit(mock_api, runner):
    mock_api.status["concurrency_limit"] = 3
    mock_api.delay = 0.01
    results = runner(items(12))
    assert all(result.ok for result in results)
    assert mock_api.peak == 3


def test_concurrency_override_only_lowers(mock_api, runner):
    mock_api.status["concurrency_limit"] = 3
    mock_api.delay = 0.01
    runner(items(6), concurrency=1)
    assert mock_api.peak == 1
    mock_api.peak = 0
    runner(items(12), concurrency=50)
    assert mock_api.peak == 3


def test_limit_change_replaces_semaphore(mock_api):
    mock_api.status["concurrency_limit"] = 3
    mock_api.delay = 0.01
    scrape(items(12))
    assert mock_api.peak == 3
    mock_api.status["concurrency_limit"] = 5
    mock_api.peak = 0
    scrape(items(12))
    assert mock_api.peak == 5


def test_large_batch_respects_limit(mock_api):
    mock_api.status["concurrency_limit"] = 300
    mock_api.delay = 0.005
    results = scrape(items(1000), tqdm_disable=True)
    assert len(results) == 1000 and all(result.ok for result in results)
    assert [result.index for result in results] == list(range(1000))
    assert mock_api.peak == 300


def test_overlapping_sync_calls_share_the_limit(mock_api):
    mock_api.status["concurrency_limit"] = 4
    mock_api.delay = 0.02
    errors: list[BaseException] = []

    def worker():
        try:
            scrape(items(12), tqdm_disable=True)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(mock_api.scrape_calls) == 24
    assert mock_api.peak == 4


def test_effective_limit_math():
    limit = _runtime.effective_limit
    assert limit(None, None, selector_limited=False) == 25
    assert limit(300, None, selector_limited=False) == 300
    assert limit(300, 50, selector_limited=False) == 50
    assert limit(300, 1000, selector_limited=False) == 300
    assert limit(1000, None, selector_limited=True) == 500
    assert limit(1000, 200, selector_limited=True) == 200


def test_selector_loop_detection():
    loop = asyncio.SelectorEventLoop()
    try:
        assert _runtime.is_selector_limited(loop) == (sys.platform == "win32")
    finally:
        loop.close()
    if sys.platform == "win32":
        proactor = asyncio.ProactorEventLoop()
        try:
            assert not _runtime.is_selector_limited(proactor)
        finally:
            proactor.close()


def test_402_mid_batch_short_circuits_remaining_items(mock_api, runner):
    mock_api.status["concurrency_limit"] = 1
    mock_api.queue(SEARCH, envelope(402, "payment_required"), success, success)
    results = runner(items(3))
    assert isinstance(results[0].error, PaymentRequiredError) and results[0].attempts == 1
    for result in results[1:]:
        assert result.error is results[0].error and result.attempts == 0
        assert result.status_code == 402
    assert len(mock_api.scrape_calls) == 1


def test_disabled_key_mid_batch_short_circuits(mock_api, runner):
    mock_api.status["concurrency_limit"] = 1
    mock_api.queue(SEARCH, envelope(403, "api_key_disabled"), success)
    results = runner(items(2))
    assert results[1].error is results[0].error and results[1].attempts == 0
    assert len(mock_api.scrape_calls) == 1


def test_missing_key_raises_before_http(mock_api, runner, monkeypatch):
    monkeypatch.delenv("LITESCRAPE_API_KEY")
    with pytest.raises(AuthenticationError) as info:
        runner([item()])
    assert info.value.error_code == "missing_api_key" and info.value.status_code is None
    assert mock_api.calls == []


def test_explicit_key_and_base_url_win(mock_api, runner):
    runner([item()], api_key="ls_live_other", base_url="https://api.test/")
    assert mock_api.calls[0].headers["authorization"] == "Bearer ls_live_other"
    assert str(mock_api.calls[0].url).startswith("https://api.test/api/")


def test_progress_bar_can_be_disabled(mock_api, capfd):
    scrape(items(3))
    assert "req" in capfd.readouterr().err
    scrape(items(3), tqdm_disable=True)
    assert capfd.readouterr().err == ""


def test_single_item_call_shows_no_bar(mock_api, capfd):
    scrape([item()])
    assert capfd.readouterr().err == ""


def test_ai_overview_without_an_overview_is_a_successful_result(mock_api, runner):
    body = {"search_metadata": {"id": "ok", "ai_overview_state": "not_served"}, "ai_overview": None}
    mock_api.queue(AI_OVERVIEW, httpx.Response(200, json=body, headers={"x-litescrape-billed": "false"}))
    (result,) = runner([GoogleAiOverview(q="nothing here")])
    assert result.ok and result.attempts == 1
    assert result.raise_for_error()["ai_overview"] is None
    assert result.data["search_metadata"]["ai_overview_state"] == "not_served"


def test_raise_for_error_returns_data(mock_api, runner):
    (result,) = runner([item()])
    assert result.raise_for_error() == result.data
    assert result.data["search_metadata"]["id"] == "ok"
    assert result.request_id == "req-ok" and result.status_code == 200 and result.elapsed >= 0


def test_empty_batch_makes_no_calls(mock_api, runner):
    assert runner([]) == []
    assert mock_api.calls == []


def test_unexpected_handler_error_becomes_result(mock_api, runner):
    mock_api.queue(SEARCH, RuntimeError("exploded"), success)
    (result,) = runner([item()])
    assert isinstance(result.error, TransportError) and "exploded" in str(result.error)
    assert result.attempts == 1 and len(mock_api.scrape_calls) == 1


@pytest.mark.parametrize("kwargs", [{"attempts": 0}, {"concurrency": 0}, {"timeout": 0}])
def test_argument_validation(mock_api, runner, kwargs):
    with pytest.raises(ValueError):
        runner([item()], **kwargs)
    assert mock_api.calls == []


def test_cancellation_stops_inflight_requests_and_backoff(mock_api, monkeypatch):
    monkeypatch.setattr(_runtime, "_sleep", asyncio.sleep)
    mock_api.delay = 5.0

    async def cancel_inflight():
        task = asyncio.create_task(ascrape(items(2), tqdm_disable=True))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
        return mock_api.in_flight

    assert asyncio.run(cancel_inflight()) == 0

    mock_api.delay = 0.0
    mock_api.queue(
        SEARCH, envelope(503, "service_unavailable", retryable=True, headers={"retry-after": "30"})
    )

    async def cancel_backoff():
        task = asyncio.create_task(ascrape([item()], tqdm_disable=True))
        await asyncio.sleep(0.1)
        started = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return time.monotonic() - started

    assert asyncio.run(cancel_backoff()) < 1.0


def test_sync_calls_reuse_one_client(mock_api):
    for _ in range(3):
        scrape([item()])
    assert mock_api.clients_made == 1


def test_scrape_works_inside_a_running_event_loop(mock_api):
    async def main():
        return scrape(items(2), tqdm_disable=True)

    results = asyncio.run(main())
    assert [result.ok for result in results] == [True, True]


def test_key_status(mock_api):
    status = key_status()
    assert status.remaining_calls == 1000 and status.concurrency_limit == 25
    assert status.status == "active" and status.request_id == "status-id"
    assert mock_api.calls[-1].url.path == STATUS_PATH


def test_sync_wrapper_is_interruptible(mock_api, monkeypatch):
    mock_api.delay = 5.0
    future_holder = {}
    original = asyncio.run_coroutine_threadsafe

    def capture(coro, loop):
        future_holder["future"] = future = original(coro, loop)
        return future

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", capture)

    class Boom(BaseException):
        pass

    calls = 0
    real_result = None

    def result(self, timeout=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise Boom
        return real_result(self, timeout)

    import concurrent.futures

    real_result = concurrent.futures.Future.result
    monkeypatch.setattr(concurrent.futures.Future, "result", result)
    with pytest.raises(Boom):
        scrape(items(2), tqdm_disable=True)
    assert future_holder["future"].cancelled() or future_holder["future"].done()
