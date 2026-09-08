from __future__ import annotations

import asyncio

import httpx
import pytest

from litescrape_sdk import (
    APIError,
    GooglePlayApps,
    GoogleSearch,
    RequestDeadlineExceededError,
    TransportError,
    ValidationError,
    ascrape,
    scrape,
)

from .conftest import envelope, success

SEARCH = "/api/google/search"


@pytest.fixture(params=["sync", "async"])
def runner(request):
    if request.param == "sync":
        return scrape
    return lambda *args, **kwargs: asyncio.run(ascrape(*args, **kwargs))


def test_server_deadline_defaults_and_item_overrides(mock_api, runner):
    original = GoogleSearch(q="default")
    results = runner(
        [
            original,
            GoogleSearch(q="override", timeout=2.5),
            {"endpoint": "google_search", "q": "dict", "timeout": 90},
            GooglePlayApps(q="store"),
        ],
        request_timeout=15,
    )
    assert all(result.ok for result in results)
    assert [result.request.timeout for result in results] == [15, 2.5, 90, 15]
    assert original.timeout is None
    assert [call.url.params["timeout"] for call in mock_api.scrape_calls] == ["15.0", "2.5", "90.0", "15.0"]
    assert all("timeout" not in call.url.params for call in mock_api.status_calls)
    assert all(call.extensions["timeout"]["read"] == 120 for call in mock_api.calls)


def test_existing_transport_timeout_does_not_set_server_deadline(mock_api, runner):
    runner([GoogleSearch(q="unchanged")], timeout=7)
    assert all("timeout" not in call.url.params for call in mock_api.calls)
    assert all(call.extensions["timeout"]["read"] == 7 for call in mock_api.calls)


@pytest.mark.parametrize("value", [0, -1, 90.01, float("nan"), float("inf"), True, "15"])
def test_invalid_default_deadline_sends_nothing(mock_api, runner, value):
    with pytest.raises(ValueError, match="request_timeout"):
        runner([GoogleSearch(q="x")], request_timeout=value)
    assert mock_api.calls == []


@pytest.mark.parametrize("value", [0, -1, 91, float("nan"), float("inf"), False])
def test_invalid_item_deadline_rejects_entire_batch(mock_api, runner, value):
    with pytest.raises(ValidationError, match="timeout"):
        runner([GoogleSearch(q="valid"), {"endpoint": "google_search", "q": "invalid", "timeout": value}])
    assert mock_api.calls == []


def test_deadline_error_preserves_contract_when_retries_disabled(mock_api, runner):
    mock_api.queue(
        SEARCH, envelope(503, "request_deadline_exceeded", retryable=True, headers={"retry-after": "10"})
    )
    (result,) = runner([GoogleSearch(q="x", timeout=0.125)], attempts=1)
    assert isinstance(result.error, RequestDeadlineExceededError)
    assert isinstance(result.error, APIError)
    assert result.status_code == result.error.status_code == 503
    assert result.request_id == result.error.request_id == "abc123"
    assert result.error.error_code == "request_deadline_exceeded"
    assert result.error.retryable is True
    assert result.error.retry_after == 10
    assert result.error.message == "request_deadline_exceeded happened"
    assert result.attempts == 1 and mock_api.sleeps == []
    assert mock_api.scrape_calls[0].url.params["timeout"] == "0.125"
    with pytest.raises(RequestDeadlineExceededError):
        result.raise_for_error()


def test_deadline_retries_follow_retry_after_and_preserve_budget(mock_api, runner):
    mock_api.queue(
        SEARCH,
        envelope(503, "request_deadline_exceeded", retryable=True, headers={"retry-after": "10"}),
        success,
    )
    (result,) = runner([GoogleSearch(q="x")], request_timeout=5, attempts=2)
    assert result.ok and result.attempts == 2
    assert mock_api.sleeps == [10]
    assert [call.url.params["timeout"] for call in mock_api.scrape_calls] == ["5.0", "5.0"]


def test_exhausted_deadlines_remain_typed_and_retryable(mock_api, runner):
    mock_api.queue(SEARCH, *[envelope(503, "request_deadline_exceeded", retryable=True)] * 2)
    (result,) = runner([GoogleSearch(q="x")], request_timeout=5, attempts=2)
    assert isinstance(result.error, RequestDeadlineExceededError)
    assert result.error.retryable and result.attempts == 2


def test_transport_timeout_is_distinct_from_server_deadline(mock_api, runner):
    mock_api.queue(SEARCH, httpx.ReadTimeout("connection timed out"))
    (result,) = runner([GoogleSearch(q="x", timeout=5)], attempts=1)
    assert isinstance(result.error, TransportError)
    assert result.request_id == "" and result.status_code is None


def test_other_503_does_not_claim_deadline_contract(mock_api, runner):
    mock_api.queue(SEARCH, envelope(503, "service_unavailable", retryable=True))
    (result,) = runner([GoogleSearch(q="x", timeout=5)], attempts=1)
    assert type(result.error) is APIError
