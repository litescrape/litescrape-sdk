# litescrape-sdk

Python SDK for the [Litescrape API](https://litescrape.com): validated, concurrent, retrying calls to the
Google, Bing, DuckDuckGo, Yelp, Tripadvisor, Apple Maps, Google Play, and Apple App Store endpoints, with results returned in input order.

```
pip install litescrape-sdk
```

```python
import os
from litescrape_sdk import GoogleMaps, scrape

os.environ["LITESCRAPE_API_KEY"] = "ls_live_..."

results = scrape(
    [
        {"endpoint": "google_search", "q": "coffee grinders", "gl": "us"},
        GoogleMaps(q="coffee", type="search", ll="@40.745,-73.988,14z"),
    ]
)
for result in results:
    print(result.ok, result.data or result.error)
```

`help(litescrape_sdk.scrape)` documents every argument, the retry and concurrency rules, and the error
types. `ascrape` is the same function for asyncio code, and `litescrape_sdk.REQUEST_TYPES` maps each
`endpoint` slug to its request class.

Development: `uv sync`, then `uv run pytest`, `uv run ruff check .`, and `uv run ruff format .`.

## Durable batches and recovery

Requires an API deployment with durable batch support. Set `batched=True` to submit every query
before polling for completion. The server continues processing accepted jobs if your computer
disconnects or the Python process exits. Responses are retained for 24 hours after completion.

```python
from litescrape_sdk import GoogleSearch, scrape

queries = [GoogleSearch(q="coffee grinders"), GoogleSearch(q="espresso machines")]
results = scrape(queries, batched=True, cache_path="./my-batch.sqlite3")

# After a crash or disconnect, rerun with the same inputs, key and cache path:
results = scrape(queries, batched=True, useCache=True, cache_path="./my-batch.sqlite3")
for result in results:
    print(result.job_id, result.data or result.error)
```

The SDK saves the entire workload's submission intentions and batch IDs before sending its first
request, then saves returned job IDs. The server provisions dedicated batch workers from accepted
inputs and assigns work as matching identities become ready. `useCache=False`
is the default and creates fresh jobs. `useCache=True` retrieves matching saved jobs; it creates
replacements only when the server confirms a job is missing or expired. A polling outage does
not trigger a fresh charge. Reordering distinct queries preserves their cache matches; identical
queries are matched by occurrence. Keep separate cache files for independently resumable batches.
The default path is `~/.cache/litescrape/jobs.sqlite3`, configurable with `LITESCRAPE_JOB_CACHE`.
The cache stores batch IDs, job IDs and request fingerprints, without raw API keys or query text.

New jobs reserve one credit; terminal failures refund that reservation. Polling and retrying the
same submission do not consume more credits. Batch mode skips the synchronous whole-list balance
check so previously paid results can be recovered even with no credits remaining. Check every
`Result` for submission errors, including insufficient credits for new jobs.

`concurrency` controls simultaneous submission/poll requests (default 32); execution uses separate
server batch capacity. Network retries and polling use exponential backoff with jitter, capped at
30 seconds; retries honor `Retry-After`. All results are returned in input order. `ascrape` accepts
the same options. A server `request_timeout` applies to each worker attempt after queueing.

## Google Search fast mode

Google Search supports `GoogleSearch(q="coffee grinders", fast_mode=True)` to
return only organic results plus search metadata and parameters. This skips
AI Overview and other result groups. The default is the full response; fast mode
is unavailable on the dedicated AI Overview endpoint. Requires an API deployment
that supports `fast_mode`.

`num` on `GoogleSearch` and `GoogleAiOverview` accepts 1 to 10, the most Google returns on one
page. Use `start` to page further.

## Fetch (Alpha)

`WebFetch` renders a public web page in a fresh browser and returns it as Markdown, HTML, plain
text, or a full-page PNG screenshot encoded as base64.

```python
from litescrape_sdk import WebFetch, scrape

[result] = scrape([WebFetch(url="https://example.com", respond_with="markdown", target_selector="article")])
page = result.raise_for_error()
print(page["title"], page["status_code"])
print(page["content"])
```

`status_code` is the status the site returned. A rendered 404 page is still a successful, billed
capture, so check it before using `content`. Options: `respond_with`, `target_selector`,
`remove_selector`, `wait_for_selector`, `wait_until`, `page_timeout`, `locale`,
`user_agent`, `with_links`, `with_images`, `with_iframe` and `with_shadow_dom`.

## Request deadlines

Set `request_timeout` on `scrape` or `ascrape` to apply a server deadline to every item.
Set `timeout` on an individual request to override that default. Both accept seconds greater than
0 and at most 90, including fractional seconds; omitting them preserves the API's standard behavior.

```python
from litescrape_sdk import GoogleSearch, RequestDeadlineExceededError, scrape

(result,) = scrape(
    [GoogleSearch(q="coffee grinders")],
    request_timeout=15,
    attempts=1,
)
if isinstance(result.error, RequestDeadlineExceededError):
    print(result.error.request_id, result.error.retryable, result.error.message)
else:
    print(result.raise_for_error())

# A per-item deadline also works in dictionaries.
results = scrape(
    [
        GoogleSearch(q="coffee", timeout=10),
        {"endpoint": "google_search", "q": "tea", "timeout": 20},
    ],
    attempts=1,
)
```

The deadline covers the entire API request from gateway receipt, including admission, scraping,
and billing. On expiry, the API returns HTTP 503 with the new `request_deadline_exceeded` code,
`retryable: true`, a request ID, and a description. That attempt is not charged. The API cancels
the underlying scrape to release concurrency; credit and concurrency cleanup can finish shortly
after the response.

The SDK retries this response using its usual `attempts` and `Retry-After` rules. Each attempt gets
its own deadline; use `attempts=1` as above to receive the first timeout immediately. SDK queueing,
the status check, network transit, retry waits, and the full batch are outside the server deadline.

The existing `scrape(..., timeout=120)` argument remains the HTTP transport timeout. Keep it longer
than the server deadline so the API can return its error. A client-side `TransportError` alone does
not guarantee that the request was unbilled.

## Store APIs (Alpha)

All nine Store operations use your existing key. Alpha fields depend on what the storefront supplies.

| Request class | Endpoint slug |
| --- | --- |
| `GooglePlayApps` | `google_play_apps` |
| `GooglePlayGames` | `google_play_games` |
| `GooglePlayBooks` | `google_play_books` |
| `GooglePlayMovies` | `google_play_movies` |
| `GooglePlayProduct` | `google_play_product` |
| `GooglePlayReviews` | `google_play_reviews` |
| `AppleAppStoreSearch` | `apple_app_store_search` |
| `AppleAppStoreProduct` | `apple_app_store_product` |
| `AppleAppStoreReviews` | `apple_app_store_reviews` |

```python
from litescrape_sdk import GooglePlayApps, GooglePlayProduct, AppleAppStoreSearch, scrape

results = scrape(
    [
        GooglePlayApps(q="coffee", hl="en", gl="us"),
        GooglePlayProduct(product_id="com.duolingo"),
        AppleAppStoreSearch(term="coffee", country="us", num=10),
    ]
)
for result in results:
    print(result.raise_for_error())
```

Follow `litescrape_pagination.next` or use the returned continuation with the same operation
and parameters. Each successful page consumes one call; failures do not. For Google Play,
`chart`, `next_page_token`, `section_page_token`, and `see_more_token` are mutually exclusive.
Queries exclude category filters and charts. Search text is limited to 2,048 UTF-8 bytes,
so non-ASCII characters can consume more than one byte. Apple search also limits
URL-encoded terms to 4,096 bytes. Apps/games charts require
`store_device="phone"` or an omitted device; other device storefronts are browsable without a chart. Omit `store_device` when using an apps or games query or category.
`GooglePlayGames(q=...)` uses the shared Android app search; omit `q` or choose `games_category`
to browse games. Apple review pages
are one-based; exhausted pages return an empty list. Mac reviews use newest-first ordering.

`search_metadata.raw_file` and `prettify_file`, when returned, link to authenticated response
artifacts retained for at least seven days (today and the previous seven UTC date buckets). Download them with the same bearer key; downloads are unbilled.
Apple search applies category and case-insensitive developer-name filters before the `num` ceiling.
The native search window can contain fewer matching results than that ceiling.
See the [API reference](https://litescrape.com/docs) for every parameter and response group.
