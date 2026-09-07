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
Queries exclude category filters. Omit `store_device` when using an apps or games query or category.
`GooglePlayGames(q=...)` uses the shared Android app search; omit `q` or choose `games_category`
to browse games. Apple review pages
are one-based; exhausted pages return an empty list. Mac reviews use newest-first ordering.

`search_metadata.raw_file` and `prettify_file`, when returned, link to authenticated response
artifacts retained for at least seven days (today and the previous seven UTC date buckets). Download them with the same bearer key; downloads are unbilled.
See the [API reference](https://litescrape.com/docs) for every parameter and response group.
