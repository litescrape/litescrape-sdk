# litescrape-sdk

Python SDK for the [Litescrape API](https://litescrape.com): validated, concurrent, retrying calls to all
139 endpoints, covering search engines (Google, Bing, Brave, DuckDuckGo, Yahoo, Yandex, Baidu, Naver), AI
answers (Google AI Mode and Gemini, Brave AI Mode, Microsoft Copilot), maps and reviews, app stores,
social platforms (YouTube, TikTok, Instagram, Facebook, X), retail, jobs, real estate, travel, and web
pages, with results returned in input order. The [endpoint table](#endpoints) lists every request class.

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

Most endpoints are sent as `GET` with query parameters. Array parameters on the job search endpoints
(`IndeedSearch(employer_keys=[...])`, `LevelsSearch(companies=[...])`, ...) are JSON-encoded in the
query for you. Four endpoints take arrays or nested objects and are sent as a JSON `POST` body instead:
`WebFetch`, `WebScreenshot`, `GoogleShoppingMerchantUrls`, and `CopilotChatCompletions`. Each class's
`method` says which, and `body()` shows the JSON it sends. eBay's underscore parameters are fields
without the underscore: `EbaySearch(nkw="lego", ipg=25)` sends `_nkw` and `_ipg`.

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
page. To page further, send `GoogleSearch(page_token=...)` alone with the `pagination.next_page_token`
from the previous response, within five minutes; `start` also still works.

## Fetch and screenshots (Alpha)

`WebFetch` renders a public web page and returns it as Markdown, HTML, or plain text;
`WebScreenshot` returns a PNG screenshot encoded as base64. Both are sent as a JSON body, so list
selectors, cookies, scripts, and a `Viewport` work directly.

```python
import base64

from litescrape_sdk import WebFetch, WebScreenshot, scrape

page, shot = scrape(
    [
        WebFetch(url="https://example.com", respond_with="markdown", target_selector=["article", "main"]),
        WebScreenshot(url="https://example.com", full_page=True, viewport={"width": 1440, "height": 900}),
    ]
)
page = page.raise_for_error()
print(page["title"], page["url"])
print(page["content"])
png = base64.b64decode(shot.raise_for_error()["screenshot_base64"])
```

A rendered error page is still a successful, billed capture unless you set `assert_status_code`
(for example `200`); a different origin status is then rejected without billing. `respond_with` is
`content` (the default), `markdown`, `html`, `text`, `frontmatter`, or a `+` combination such as
`markdown+frontmatter`. Screenshots moved from `respond_with="screenshot"` to `WebScreenshot`.
The 0.6 options `wait_until`, `with_links`, and `with_images` are replaced by `respond_timing`,
`retain_links`, and `retain_images`.

## Copilot and merchant URLs

```python
from litescrape_sdk import CopilotChatCompletions, GoogleShoppingMerchantUrls, scrape

results = scrape(
    [
        CopilotChatCompletions(
            messages=[{"role": "user", "content": "What is the weather near me right now?"}],
            country="US",
            state="CA",
        ),
        GoogleShoppingMerchantUrls(
            products=[{"headline_offer_docid": "5148952067814683768", "merchant": "Target"}]
        ),
    ]
)
answer = results[0].raise_for_error()
print(answer["choices"][0]["message"]["content"])
```

Each Copilot call starts a fresh conversation; resend earlier messages for context. The last message
must have role `user`. Merchant URL lookups take 1 to 100 headline offers copied from a
`GoogleShopping` result.

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

## Store APIs

The nine Google Play and Apple App Store operations (`GooglePlayApps` through
`AppleAppStoreReviews` in the [endpoint table](#endpoints)) use your existing key. Fields depend on
what the storefront supplies.

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

## Endpoints

Alpha endpoints are newer; their response fields can change as the sources do.

| Request class | Endpoint slug | Route | Status |
| --- | --- | --- | --- |
| `GoogleSearch` | `google_search` | `GET /api/google/search` |  |
| `GoogleAiOverview` | `google_ai_overview` | `GET /api/google/ai-overview` |  |
| `GoogleAiMode` | `google_ai_mode` | `GET /api/google/ai-mode` |  |
| `GoogleGemini` | `google_gemini` | `GET /api/google/gemini` |  |
| `GoogleAds` | `google_ads` | `GET /api/google/ads` | Alpha |
| `GoogleShopping` | `google_shopping` | `GET /api/google/shopping` |  |
| `GoogleShoppingProduct` | `google_shopping_product` | `GET /api/google/shopping/product` |  |
| `GoogleShoppingMerchantUrls` | `google_shopping_merchant_urls` | `POST /api/google/shopping/merchant-urls` |  |
| `GoogleLocal` | `google_local` | `GET /api/google/local` |  |
| `GoogleImages` | `google_images` | `GET /api/google/images` |  |
| `GoogleJobs` | `google_jobs` | `GET /api/google/jobs` |  |
| `GoogleMaps` | `google_maps` | `GET /api/google/maps` |  |
| `GoogleMapsLiveFootTraffic` | `google_maps_live_foot_traffic` | `GET /api/google/maps/popular-times` |  |
| `GoogleMapsPosts` | `google_maps_posts` | `GET /api/google/maps/posts` |  |
| `GoogleMapsPhoto` | `google_maps_photo` | `GET /api/google/maps/photo-meta` |  |
| `GoogleReviews` | `google_reviews` | `GET /api/google/reviews` |  |
| `GoogleContributorReviews` | `google_contributor_reviews` | `GET /api/google/contributor-reviews` |  |
| `BingSearch` | `bing_search` | `GET /api/bing/search` |  |
| `BingMaps` | `bing_maps` | `GET /api/bing/maps` |  |
| `BingImages` | `bing_images` | `GET /api/bing/images` |  |
| `BingShopping` | `bing_shopping` | `GET /api/bing/shopping` |  |
| `BingProduct` | `bing_product` | `GET /api/bing/product` |  |
| `DuckDuckGoSearch` | `duckduckgo_search` | `GET /api/duckduckgo/search` |  |
| `DuckDuckGoMaps` | `duckduckgo_maps` | `GET /api/duckduckgo/maps` |  |
| `YelpSearch` | `yelp_search` | `GET /api/yelp/search` |  |
| `YelpReviews` | `yelp_reviews` | `GET /api/yelp/reviews` |  |
| `YelpPlace` | `yelp_place` | `GET /api/yelp/place` |  |
| `TripadvisorSearch` | `tripadvisor_search` | `GET /api/tripadvisor/search` |  |
| `TripadvisorPlace` | `tripadvisor_place` | `GET /api/tripadvisor/place` |  |
| `TripadvisorReviews` | `tripadvisor_reviews` | `GET /api/tripadvisor/reviews` |  |
| `AppleMapsPlaces` | `apple_maps_places` | `GET /api/apple/maps/places` |  |
| `AppleMapsReviews` | `apple_maps_reviews` | `GET /api/apple/maps/reviews` |  |
| `GooglePlayApps` | `google_play_apps` | `GET /api/google/play/apps` |  |
| `GooglePlayGames` | `google_play_games` | `GET /api/google/play/games` |  |
| `GooglePlayBooks` | `google_play_books` | `GET /api/google/play/books` |  |
| `GooglePlayMovies` | `google_play_movies` | `GET /api/google/play/movies` |  |
| `GooglePlayProduct` | `google_play_product` | `GET /api/google/play/product` |  |
| `GooglePlayReviews` | `google_play_reviews` | `GET /api/google/play/reviews` |  |
| `AppleAppStoreSearch` | `apple_app_store_search` | `GET /api/apple/app-store/search` |  |
| `AppleAppStoreProduct` | `apple_app_store_product` | `GET /api/apple/app-store/product` |  |
| `AppleAppStoreReviews` | `apple_app_store_reviews` | `GET /api/apple/app-store/reviews` |  |
| `WebFetch` | `web_fetch` | `POST /api/web/fetch` | Alpha |
| `WebScreenshot` | `web_screenshot` | `POST /api/web/screenshot` | Alpha |
| `BraveSearch` | `brave_search` | `GET /api/brave/search` |  |
| `BraveAiMode` | `brave_ai_mode` | `GET /api/brave/ai-mode` |  |
| `BaiduSearch` | `baidu_search` | `GET /api/baidu/search` |  |
| `YandexSearch` | `yandex_search` | `GET /api/yandex/search` |  |
| `YandexImages` | `yandex_images` | `GET /api/yandex/images` |  |
| `NaverSearch` | `naver_search` | `GET /api/naver/search` |  |
| `NaverAiOverview` | `naver_ai_overview` | `GET /api/naver/ai-overview` |  |
| `CopilotChatCompletions` | `copilot_chat_completions` | `POST /api/copilot/chat/completions` | Alpha |
| `YahooSearch` | `yahoo_search` | `GET /api/yahoo/search` |  |
| `YahooImages` | `yahoo_images` | `GET /api/yahoo/images` |  |
| `AirbnbSearch` | `airbnb_search` | `GET /api/airbnb/search` |  |
| `EventbriteSearch` | `eventbrite_search` | `GET /api/eventbrite/search` |  |
| `IndeedSearch` | `indeed_search` | `GET /api/indeed/search` |  |
| `GlassdoorSearch` | `glassdoor_search` | `GET /api/glassdoor/search` |  |
| `AshbySearch` | `ashby_search` | `GET /api/ashby/search` |  |
| `ZipRecruiterSearch` | `ziprecruiter_search` | `GET /api/ziprecruiter/search` |  |
| `LevelsSearch` | `levels_search` | `GET /api/levels/search` |  |
| `ZillowSearch` | `zillow_search` | `GET /api/zillow/search` |  |
| `ZillowProperty` | `zillow_property` | `GET /api/zillow/property` |  |
| `ZillowLocations` | `zillow_locations` | `GET /api/zillow/locations` |  |
| `RedfinSearch` | `redfin_search` | `GET /api/redfin/search` |  |
| `RedfinProperty` | `redfin_property` | `GET /api/redfin/property` |  |
| `RealtorSearch` | `realtor_search` | `GET /api/realtor/search` | Alpha |
| `RealtorProperty` | `realtor_property` | `GET /api/realtor/property` | Alpha |
| `ApartmentsSearch` | `apartments_search` | `GET /api/apartments/search` | Alpha |
| `ApartmentsProperty` | `apartments_property` | `GET /api/apartments/property` | Alpha |
| `HomesSearch` | `homes_search` | `GET /api/homes/search` | Alpha |
| `HomesProperty` | `homes_property` | `GET /api/homes/property` | Alpha |
| `FacebookSearchPages` | `facebook_search_pages` | `GET /api/facebook/search-pages` | Alpha |
| `FacebookSearchProfiles` | `facebook_search_profiles` | `GET /api/facebook/search-profiles` | Alpha |
| `FacebookHashtagPosts` | `facebook_hashtag_posts` | `GET /api/facebook/hashtag-posts` | Alpha |
| `FacebookPost` | `facebook_post` | `GET /api/facebook/post` | Alpha |
| `FacebookPagePosts` | `facebook_page_posts` | `GET /api/facebook/page-posts` | Alpha |
| `FacebookMarketplaceBrowse` | `facebook_marketplace_browse` | `GET /api/facebook/marketplace-browse` | Alpha |
| `FacebookReel` | `facebook_reel` | `GET /api/facebook/reel` | Alpha |
| `YouTubeSearch` | `youtube_search` | `GET /api/youtube/search` |  |
| `YouTubeChannel` | `youtube_channel` | `GET /api/youtube/channel` |  |
| `AmazonSearch` | `amazon_search` | `GET /api/amazon/search` | Alpha |
| `AmazonProduct` | `amazon_product` | `GET /api/amazon/product` | Alpha |
| `AmazonAutocomplete` | `amazon_autocomplete` | `GET /api/amazon/autocomplete` | Alpha |
| `AmazonFeaturedReviews` | `amazon_featured_reviews` | `GET /api/amazon/featured-reviews` | Alpha |
| `AmazonMediaReviews` | `amazon_media_reviews` | `GET /api/amazon/media-reviews` | Alpha |
| `XProfile` | `x_profile` | `GET /api/x/profile` | Alpha |
| `XPost` | `x_post` | `GET /api/x/post` | Alpha |
| `XUserPosts` | `x_user_posts` | `GET /api/x/user-posts` | Alpha |
| `XCommunity` | `x_community` | `GET /api/x/community` | Alpha |
| `XCommunityPosts` | `x_community_posts` | `GET /api/x/community-posts` | Alpha |
| `EbaySearch` | `ebay_search` | `GET /api/ebay/search` |  |
| `EbayProduct` | `ebay_product` | `GET /api/ebay/product` |  |
| `EbaySeller` | `ebay_seller` | `GET /api/ebay/seller` |  |
| `TikTokProfile` | `tiktok_profile` | `GET /api/tiktok/profile` | Alpha |
| `TikTokVideo` | `tiktok_video` | `GET /api/tiktok/video` | Alpha |
| `TikTokTranscript` | `tiktok_transcript` | `GET /api/tiktok/transcript` | Alpha |
| `TikTokSearchSuggestions` | `tiktok_search_suggestions` | `GET /api/tiktok/search-suggestions` | Alpha |
| `TikTokUserLive` | `tiktok_user_live` | `GET /api/tiktok/user-live` | Alpha |
| `TikTokLive` | `tiktok_live` | `GET /api/tiktok/live` | Alpha |
| `TikTokSong` | `tiktok_song` | `GET /api/tiktok/song` | Alpha |
| `TikTokProfileVideos` | `tiktok_profile_videos` | `GET /api/tiktok/profile-videos` | Alpha |
| `TikTokComments` | `tiktok_comments` | `GET /api/tiktok/comments` | Alpha |
| `TikTokCommentReplies` | `tiktok_comment_replies` | `GET /api/tiktok/comment-replies` | Alpha |
| `TikTokFollowing` | `tiktok_following` | `GET /api/tiktok/following` | Alpha |
| `TikTokFollowers` | `tiktok_followers` | `GET /api/tiktok/followers` | Alpha |
| `TikTokSearchKeyword` | `tiktok_search_keyword` | `GET /api/tiktok/search-keyword` | Alpha |
| `TikTokSearchTop` | `tiktok_search_top` | `GET /api/tiktok/search-top` | Alpha |
| `TikTokSearchHashtag` | `tiktok_search_hashtag` | `GET /api/tiktok/search-hashtag` | Alpha |
| `TikTokSongVideos` | `tiktok_song_videos` | `GET /api/tiktok/song-videos` | Alpha |
| `TikTokTrendingFeed` | `tiktok_trending_feed` | `GET /api/tiktok/trending-feed` | Alpha |
| `TikTokCollectionVideos` | `tiktok_collection_videos` | `GET /api/tiktok/collection-videos` | Alpha |
| `InstagramProfile` | `instagram_profile` | `GET /api/instagram/profile` | Alpha |
| `InstagramPosts` | `instagram_posts` | `GET /api/instagram/posts` | Alpha |
| `InstagramPost` | `instagram_post` | `GET /api/instagram/post` | Alpha |
| `InstagramProfilePostCount` | `instagram_profile_post_count` | `GET /api/instagram/profile-post-count` | Alpha |
| `InstagramEmbed` | `instagram_embed` | `GET /api/instagram/embed` | Alpha |
| `InstagramSearchPopular` | `instagram_search_popular` | `GET /api/instagram/search-popular` | Alpha |
| `WalmartSearch` | `walmart_search` | `GET /api/walmart/search` | Alpha |
| `WalmartProduct` | `walmart_product` | `GET /api/walmart/product` | Alpha |
| `HomeDepotSearch` | `homedepot_search` | `GET /api/homedepot/search` | Alpha |
| `HomeDepotProduct` | `homedepot_product` | `GET /api/homedepot/product` | Alpha |
| `TargetSearch` | `target_search` | `GET /api/target/search` | Alpha |
| `TargetProduct` | `target_product` | `GET /api/target/product` | Alpha |
| `EtsySearch` | `etsy_search` | `GET /api/etsy/search` | Alpha |
| `EtsyProduct` | `etsy_product` | `GET /api/etsy/product` | Alpha |
| `BestBuySearch` | `bestbuy_search` | `GET /api/bestbuy/search` | Alpha |
| `BestBuyProduct` | `bestbuy_product` | `GET /api/bestbuy/product` | Alpha |
| `WayfairSearch` | `wayfair_search` | `GET /api/wayfair/search` | Alpha |
| `WayfairProduct` | `wayfair_product` | `GET /api/wayfair/product` | Alpha |
| `AliExpressSearch` | `aliexpress_search` | `GET /api/aliexpress/search` | Alpha |
| `AliExpressProduct` | `aliexpress_product` | `GET /api/aliexpress/product` | Alpha |
| `KrogerSearch` | `kroger_search` | `GET /api/kroger/search` | Alpha |
| `KrogerProduct` | `kroger_product` | `GET /api/kroger/product` | Alpha |
| `SproutsSearch` | `sprouts_search` | `GET /api/sprouts/search` | Alpha |
| `SproutsProduct` | `sprouts_product` | `GET /api/sprouts/product` | Alpha |
| `WholeFoodsSearch` | `wholefoods_search` | `GET /api/wholefoods/search` | Alpha |
| `WholeFoodsProduct` | `wholefoods_product` | `GET /api/wholefoods/product` | Alpha |
| `IkeaSearch` | `ikea_search` | `GET /api/ikea/search` | Alpha |
| `IkeaProduct` | `ikea_product` | `GET /api/ikea/product` | Alpha |
