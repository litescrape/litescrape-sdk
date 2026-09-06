# litescrape-sdk

Python SDK for the [Litescrape API](https://litescrape.com): validated, concurrent, retrying calls to the
Google, Bing, DuckDuckGo, Yelp, Tripadvisor, and Apple Maps endpoints, with results returned in input order.

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
