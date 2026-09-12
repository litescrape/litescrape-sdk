from __future__ import annotations

import asyncio

import httpx
import pytest

from litescrape_sdk import GoogleSearch, ascrape, scrape
from litescrape_sdk._batch import JobCache, cache_keys


def backend(api):
    jobs = {}
    submissions = []

    def handle(request):
        if request.method == "POST":
            key = request.headers["idempotency-key"]
            submissions.append(key)
            if key not in jobs:
                jobs[key] = {"job_id": f"job-{len(jobs)}", "state": "queued"}
            return httpx.Response(202, json=jobs[key])
        job_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "job_id": job_id,
                "state": "succeeded",
                "status_code": 200,
                "response": {"answer": job_id},
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )

    api.default = handle
    return jobs, submissions


def test_submit_all_before_polling_and_resume_without_balance_check(mock_api, tmp_path):
    _, submissions = backend(mock_api)
    items = [GoogleSearch(q="a"), GoogleSearch(q="b")]
    options = {"batched": True, "cache_path": tmp_path / "jobs.db", "tqdm_disable": True}
    results = scrape(items, **options)
    assert all(r.ok and r.job_id for r in results)
    methods = [r.method for r in mock_api.calls]
    assert methods == ["POST", "POST", "GET", "GET"]
    mock_api.status["remaining_calls"] = 0
    mock_api.calls.clear()
    resumed = scrape(list(reversed(items)), useCache=True, **options)
    assert [r.data for r in resumed] == [r.data for r in reversed(results)]
    assert all(r.method == "GET" and "/batch/jobs/" in r.url.path for r in mock_api.calls)
    assert len(submissions) == 2


def test_identical_items_have_distinct_ids_and_default_makes_fresh_jobs(mock_api, tmp_path):
    backend(mock_api)
    items = [GoogleSearch(q="same")] * 2
    options = {"batched": True, "cache_path": tmp_path / "jobs.db", "tqdm_disable": True}
    first = scrape(items, **options)
    assert first[0].job_id != first[1].job_id
    assert [r.job_id for r in scrape(items, useCache=True, **options)] == [r.job_id for r in first]
    assert set(r.job_id for r in scrape(items, **options)).isdisjoint(r.job_id for r in first)


def test_lost_submission_acknowledgement_recovers_same_intent_after_restart(mock_api, tmp_path):
    jobs, submissions = backend(mock_api)
    original = mock_api.default
    lost = True

    def handle(request):
        nonlocal lost
        result = original(request)
        if request.method == "POST" and lost:
            lost = False
            raise httpx.ReadError("response lost", request=request)
        return result

    mock_api.default = handle
    options = {"batched": True, "cache_path": tmp_path / "jobs.db", "attempts": 1, "tqdm_disable": True}
    result = scrape([GoogleSearch(q="a")], **options)[0]
    assert not result.ok
    result = scrape([GoogleSearch(q="a")], useCache=True, **options)[0]
    assert result.ok
    assert len(jobs) == 1 and len(submissions) == 2 and submissions[0] == submissions[1]


def test_poll_outage_never_submits_replacement_job(mock_api, tmp_path):
    _, submissions = backend(mock_api)
    options = {"batched": True, "cache_path": tmp_path / "jobs.db", "attempts": 2, "tqdm_disable": True}
    items = [GoogleSearch(q="a")]
    first = scrape(items, **options)[0]
    mock_api.queue(
        "/api/batch/jobs/" + first.job_id,
        httpx.Response(503, json={"error": "unavailable"}),
        httpx.Response(503, json={"error": "unavailable"}),
    )
    assert not scrape(items, useCache=True, **options)[0].ok
    assert len(submissions) == 1
    assert scrape(items, useCache=True, **options)[0].ok


@pytest.mark.parametrize("status", [404, 410])
def test_definitively_missing_or_expired_cache_id_creates_new_job(mock_api, tmp_path, status):
    _, submissions = backend(mock_api)
    options = {"batched": True, "cache_path": tmp_path / "jobs.db", "tqdm_disable": True}
    items = [GoogleSearch(q="a")]
    first = scrape(items, **options)[0]
    mock_api.queue("/api/batch/jobs/" + first.job_id, httpx.Response(status, json={"error": "expired"}))
    second = scrape(items, useCache=True, **options)[0]
    assert second.ok and second.job_id != first.job_id
    assert len(submissions) == 2


def test_submission_retries_keep_idempotency_key_and_exponential_backoff(mock_api, tmp_path):
    backend(mock_api)
    mock_api.queue(
        "/api/google/search/async", *[httpx.Response(503, json={"error": "retry"}) for _ in range(3)]
    )
    result = scrape([GoogleSearch(q="a")], batched=True, cache_path=tmp_path / "jobs.db", attempts=4)[0]
    assert result.ok
    posts = [r for r in mock_api.calls if r.method == "POST"]
    assert len(posts) == 4
    assert len({r.headers["idempotency-key"] for r in posts}) == 1
    assert 0.5 <= mock_api.sleeps[0] <= 1
    assert 1 <= mock_api.sleeps[1] <= 2
    assert 2 <= mock_api.sleeps[2] <= 4


def test_cancellation_keeps_jobs_recoverable(mock_api, tmp_path):
    _, submissions = backend(mock_api)
    original = mock_api.default
    options = {"batched": True, "cache_path": tmp_path / "jobs.db", "tqdm_disable": True}

    async def exercise():
        entered = asyncio.Event()

        async def handle(request):
            if request.method == "GET":
                entered.set()
                await asyncio.Event().wait()
            return original(request)

        mock_api.default = handle
        task = asyncio.create_task(ascrape([GoogleSearch(q="a")], **options))
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        mock_api.default = original
        result = (await ascrape([GoogleSearch(q="a")], useCache=True, **options))[0]
        assert result.ok and len(submissions) == 1

    asyncio.run(exercise())


def test_cache_is_scoped_by_key_origin_parameters_and_duplicate_ordinal(tmp_path):
    items = [GoogleSearch(q="secret query"), GoogleSearch(q="secret query")]
    keys = cache_keys(items, "secret-key", "https://one.test")
    assert len(set(keys)) == 2
    assert keys != cache_keys(items, "other-key", "https://one.test")
    assert keys != cache_keys(items, "secret-key", "https://two.test")
    cache = JobCache(tmp_path / "jobs.db")
    for key in keys:
        cache.prepare(key, False)
    assert b"secret-key" not in cache.path.read_bytes()
    assert b"secret query" not in cache.path.read_bytes()


def test_use_cache_requires_batch_mode(mock_api):
    with pytest.raises(ValueError, match="batched"):
        scrape([GoogleSearch(q="a")], useCache=True)


def test_expired_lost_acknowledgement_intent_is_replaced_only_after_confirmation(mock_api, tmp_path):
    jobs, submissions = backend(mock_api)
    items = [GoogleSearch(q="a")]
    options = {"batched": True, "cache_path": tmp_path / "jobs.db", "attempts": 1, "tqdm_disable": True}
    original = mock_api.default

    def lost_ack(request):
        result = original(request)
        if request.method == "POST":
            raise httpx.ReadError("lost acknowledgement", request=request)
        return result

    mock_api.default = lost_ack
    assert not scrape(items, **options)[0].ok
    old_submission = submissions[0]
    jobs[old_submission]["state"] = "expired"
    mock_api.default = original
    assert scrape(items, useCache=True, **options)[0].ok
    assert submissions[:2] == [old_submission, old_submission]
    assert len(submissions) == 3 and submissions[2] != old_submission


def test_poll_rounds_collect_later_jobs_while_first_job_is_pending(mock_api, tmp_path):
    backend(mock_api)
    original = mock_api.default
    polls = []

    def pending_first(request):
        result = original(request)
        if request.method == "GET":
            job_id = request.url.path.rsplit("/", 1)[-1]
            polls.append(job_id)
            if job_id == "job-0" and polls.count(job_id) < 3:
                return httpx.Response(200, json={"job_id": job_id, "state": "running"})
        return result

    mock_api.default = pending_first
    results = scrape(
        [GoogleSearch(q=str(i)) for i in range(20)],
        batched=True,
        concurrency=2,
        cache_path=tmp_path / "jobs.db",
        tqdm_disable=True,
    )
    assert all(result.ok for result in results)
    assert polls.index("job-19") < max(i for i, job in enumerate(polls) if job == "job-0")
