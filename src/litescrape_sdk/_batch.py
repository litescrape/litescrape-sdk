"""Persist submission intent before POST, submit every item, then poll durable jobs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from tqdm import tqdm

from . import _runtime
from .errors import APIError, TransportError, api_error_from_response


class JobCache:
    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(
            path
            or os.environ.get("LITESCRAPE_JOB_CACHE")
            or Path.home() / ".cache" / "litescrape" / "jobs.sqlite3"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                cache_key TEXT PRIMARY KEY, submission TEXT NOT NULL, job_id TEXT,
                expires_at TEXT, updated_at REAL NOT NULL)""")
            connection.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "batch_key" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN batch_key TEXT")
            if "batch_size" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN batch_size INTEGER")
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        # Open per operation; independent event loops/processes may resume the
        # same batch. FULL synchronous commits make the pre-POST intent durable.
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA synchronous=FULL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def prepare(self, cache_key: str, use_cache: bool, batch_key=None, batch_size=1) -> dict:
        return self.prepare_many([cache_key], use_cache, batch_key or uuid.uuid4().hex, batch_size)[0]

    def prepare_many(self, keys, use_cache, batch_key, batch_size):
        """Commit the entire workload's intentions before sending its first input."""
        entries = []
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for cache_key in keys:
                row = connection.execute(
                    "SELECT submission,job_id,batch_key,batch_size FROM jobs WHERE cache_key=?", (cache_key,)
                ).fetchone()
                if use_cache and row:
                    entry = dict(zip(("submission", "job_id", "batch_key", "batch_size"), row, strict=True))
                    if not entry["batch_key"]:
                        entry.update(batch_key=batch_key, batch_size=batch_size)
                        connection.execute(
                            "UPDATE jobs SET batch_key=?,batch_size=? WHERE cache_key=?",
                            (batch_key, batch_size, cache_key),
                        )
                else:
                    entry = {
                        "submission": uuid.uuid4().hex,
                        "job_id": None,
                        "batch_key": batch_key,
                        "batch_size": batch_size,
                    }
                    connection.execute(
                        """INSERT INTO jobs(cache_key,submission,updated_at,batch_key,batch_size)
                        VALUES (?,?,?,?,?)
                        ON CONFLICT(cache_key) DO UPDATE SET submission=excluded.submission,
                        job_id=NULL,expires_at=NULL,updated_at=excluded.updated_at,
                        batch_key=excluded.batch_key,batch_size=excluded.batch_size""",
                        (cache_key, entry["submission"], time.time(), batch_key, batch_size),
                    )
                entries.append(entry)
        return entries

    def save(self, cache_key: str, submission: str, job: dict):
        with self.connect() as connection:
            # A fresh concurrent run may have replaced this cache slot.
            connection.execute(
                """UPDATE jobs SET job_id=?,expires_at=?,updated_at=?
                WHERE cache_key=? AND submission=?""",
                (job["job_id"], job.get("expires_at"), time.time(), cache_key, submission),
            )


def cache_keys(items, api_key: str, base_url: str) -> list[str]:
    identity = hashlib.sha256(api_key.encode()).hexdigest()
    occurrences: Counter[str] = Counter()
    keys = []
    for item in items:
        canonical = json.dumps(
            [identity, base_url, item.path, item.query_params()], sort_keys=True, separators=(",", ":")
        )
        occurrence = occurrences[canonical]
        occurrences[canonical] += 1
        # Repeated identical items remain separate billed jobs, while changing
        # unrelated items or reordering requests does not invalidate their cache.
        keys.append(hashlib.sha256(f"{canonical}:{occurrence}".encode()).hexdigest())
    return keys


async def run(
    items, *, client, key, url, headers, attempts, timeout, concurrency, use_cache, cache_path, tqdm_disable
):
    from .client import Result

    cache = JobCache(cache_path)
    keys = cache_keys(items, key, url)
    limit = concurrency or 32
    if _runtime.is_selector_limited(asyncio.get_running_loop()):
        limit = min(limit, _runtime.SELECTOR_LOOP_CAP)
    semaphore = asyncio.Semaphore(limit)
    started = time.monotonic()
    batch_key = uuid.uuid4().hex
    entries = await asyncio.to_thread(cache.prepare_many, keys, use_cache, batch_key, len(items))

    async def poll_once(job_id):
        return await _runtime.request_with_retries(
            client,
            "/api/batch/jobs/" + job_id,
            {},
            headers=headers,
            attempts=attempts,
            timeout=timeout,
            semaphore=semaphore,
        )

    async def submit(index, replace_expired=False):
        entry = entries[index]
        if replace_expired:
            entry = await asyncio.to_thread(cache.prepare, keys[index], False, batch_key, len(items))
        if entry["job_id"]:
            outcome = await poll_once(entry["job_id"])
            if outcome.error is None:
                return entry, outcome
            if outcome.status_code not in (404, 410):
                return entry, outcome  # An outage is not permission to bill again.
            entry = await asyncio.to_thread(cache.prepare, keys[index], False, batch_key, len(items))
        outcome = await _runtime.request_with_retries(
            client,
            items[index].path + "/async",
            {},
            headers={
                **headers,
                "Idempotency-Key": entry["submission"],
                "X-Litescrape-Batch-ID": entry["batch_key"],
                "X-Litescrape-Batch-Size": str(entry["batch_size"]),
            },
            attempts=attempts,
            timeout=timeout,
            semaphore=semaphore,
            method="POST",
            json_body=items[index].query_params(),
            accepted_statuses=(200, 202),
        )
        if outcome.error is None:
            job = outcome.data or {}
            if not isinstance(job.get("job_id"), str) or not job["job_id"]:
                outcome.error = TransportError("Batch submission returned no job ID.", retryable=True)
            else:
                entry["job_id"] = job["job_id"]
                await asyncio.to_thread(cache.save, keys[index], entry["submission"], job)
                if job.get("state") == "expired" and use_cache and not replace_expired:
                    # A lost POST acknowledgement may leave only the intention
                    # in the cache until after the retained result has expired.
                    return await submit(index, replace_expired=True)
        return entry, outcome

    # Two distinct phases: no waiting for newly submitted jobs to complete
    # before the server has been given the entire workload.
    async def each(indices, operation):
        # Bounded tasks also bound SQLite executor work for very large inputs.
        pending = iter(indices)

        async def worker():
            for index in pending:
                await operation(index)

        tasks = [asyncio.create_task(worker()) for _ in range(min(limit, len(indices)))]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    submissions: list[Any] = [None] * len(items)

    async def save_submission(index):
        submissions[index] = await submit(index)

    await each(range(len(items)), save_submission)

    async def resolve(index, entry, outcome):
        if outcome.error is None:
            job = outcome.data or {}
            if job.get("state") in ("succeeded", "failed"):
                status = job.get("status_code")
                payload = job.get("response")
                if not isinstance(status, int) or not isinstance(payload, dict):
                    outcome.error = TransportError("Batch job returned an invalid response.", retryable=False)
                else:
                    await asyncio.to_thread(cache.save, keys[index], entry["submission"], job)
                    error = (
                        None
                        if status == 200
                        else api_error_from_response(httpx.Response(status, json=payload))
                    )
                    return Result(
                        index=index,
                        request=items[index],
                        data=payload if error is None else None,
                        error=error,
                        status_code=status,
                        request_id=job["job_id"],
                        attempts=outcome.attempts,
                        elapsed=time.monotonic() - started,
                        job_id=job["job_id"],
                    )
            elif job.get("state") == "expired":
                outcome.error = APIError(
                    "The retained batch response expired.",
                    status_code=410,
                    error_code="job_expired",
                    request_id=entry["job_id"] or "",
                )
                outcome.status_code = 410
            elif job.get("state") not in ("queued", "running"):
                outcome.error = TransportError("Batch job returned an unknown state.", retryable=False)
            else:
                return None
        return Result(
            index=index,
            request=items[index],
            data=None,
            error=outcome.error,
            status_code=outcome.status_code,
            request_id=entry["job_id"] or outcome.request_id,
            attempts=outcome.attempts,
            elapsed=time.monotonic() - started,
            job_id=entry["job_id"] or "",
        )

    results: list[Any] = [None] * len(items)
    bar = tqdm(total=len(items), disable=tqdm_disable or len(items) == 1, unit="req")

    async def collect(index):
        entry, outcome = submissions[index]
        result = await resolve(index, entry, outcome)
        if result is None:
            outcome = await poll_once(entry["job_id"])
            submissions[index] = entry, outcome
            result = await resolve(index, entry, outcome)
        if result is not None:
            results[index] = result
            submissions[index] = None
            bar.update(1)

    try:
        pending = list(range(len(items)))
        polls = 0
        while pending:
            await each(pending, collect)
            pending = [index for index in pending if results[index] is None]
            if pending:
                polls += 1
                await _runtime._sleep(_runtime._delay(polls, None))
    finally:
        bar.close()
    return results
