"""Request models: one class per endpoint, joined by the ``endpoint`` discriminator."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, TypeAdapter, model_validator

from ._app_store import AppleProductRequest, AppleReviewsRequest, AppleSearchRequest
from ._play import (
    PlayAppsRequest,
    PlayBooksRequest,
    PlayGamesRequest,
    PlayMoviesRequest,
    PlayProductRequest,
    PlayReviewsRequest,
)


def _as_query(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _flag(value: Any) -> Any:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return value


def _stringify(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return str(value)
    return value


def _present(model: BaseModel, *names: str) -> list[str]:
    return [name for name in names if getattr(model, name) is not None]


def _require_any(model: BaseModel, *names: str) -> None:
    if not _present(model, *names):
        raise ValueError(f"one of {', '.join(names)} is required")


def _exactly_one(model: BaseModel, *names: str) -> None:
    if len(_present(model, *names)) != 1:
        raise ValueError(f"exactly one of {', '.join(names)} is required")


def _at_most_one(model: BaseModel, *names: str) -> None:
    found = _present(model, *names)
    if len(found) > 1:
        raise ValueError(f"{' and '.join(found)} cannot be combined")


def _paired(model: BaseModel, first: str, second: str) -> None:
    if (getattr(model, first) is None) != (getattr(model, second) is None):
        raise ValueError(f"{first} and {second} must be given together")


def _requires(model: BaseModel, name: str, dependency: str) -> None:
    if getattr(model, name) is not None and getattr(model, dependency) is None:
        raise ValueError(f"{name} requires {dependency}")


Flag = Annotated[Literal["0", "1"], BeforeValidator(_flag)]
Device = Literal["desktop", "tablet", "mobile"]
TimeoutSeconds = Annotated[float, Field(gt=0, le=90, allow_inf_nan=False, strict=True)]


class ScrapeRequest(BaseModel):
    """Base of every endpoint request. Subclasses set ``path`` and the ``endpoint`` literal."""

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)
    path: ClassVar[str]
    timeout: TimeoutSeconds | None = None

    def query_params(self) -> dict[str, str]:
        dumped = self.model_dump(exclude_none=True, exclude={"endpoint"})
        return {name: _as_query(value) for name, value in dumped.items()}


class _GoogleLocale(ScrapeRequest):
    hl: str | None = None
    gl: str | None = None
    google_domain: str | None = None


class _GoogleOrigin(ScrapeRequest):
    location: str | None = None
    uule: str | None = None

    @model_validator(mode="after")
    def _check_origin(self) -> _GoogleOrigin:
        _at_most_one(self, "location", "uule")
        return self


class _GoogleSearchFields(_GoogleLocale):
    q: str | None = None
    ludocid: str | None = None
    kgmid: str | None = None
    location: str | None = None
    uule: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius: float | None = None
    lsig: str | None = None
    si: str | None = None
    ibp: str | None = None
    uds: str | None = None
    color_scheme: Literal["light", "dark"] | None = None
    cr: str | None = None
    lr: str | None = None
    tbs: str | None = None
    safe: Literal["active", "off"] | None = None
    nfpr: Flag | None = None
    filter: Flag | None = None
    pws: Flag | None = None
    peek_pws: Flag | None = None
    tbm: Literal["lcl", "vid", "nws", "shop", "pts"] | None = None
    start: int | None = None
    num: Annotated[int, Field(ge=1, le=10)] | None = None
    device: Device | None = None
    oq: str | None = None
    gs_lp: str | None = None
    sclient: str | None = None
    as_dt: Literal["i", "e"] | None = None
    as_epq: str | None = None
    as_eq: str | None = None
    as_lq: str | None = None
    as_nlo: str | None = None
    as_nhi: str | None = None
    as_oq: str | None = None
    as_q: str | None = None
    as_qdr: str | None = None
    as_rq: str | None = None
    as_sitesearch: str | None = None

    @model_validator(mode="after")
    def _check_search(self) -> _GoogleSearchFields:
        _require_any(self, "q", "ludocid", "kgmid")
        _paired(self, "lat", "lon")
        _at_most_one(self, "location", "uule", "lat")
        _paired(self, "as_nlo", "as_nhi")
        _requires(self, "as_dt", "as_sitesearch")
        return self


class GoogleSearch(_GoogleSearchFields):
    """GET /api/google/search"""

    path: ClassVar[str] = "/api/google/search"
    endpoint: Literal["google_search"] = "google_search"
    fast_mode: StrictBool | Literal["true", "false"] | None = None


class GoogleAiOverview(_GoogleSearchFields):
    """GET /api/google/ai-overview

    ``ai_overview`` is None and the call is not billed when Google shows no overview.
    """

    path: ClassVar[str] = "/api/google/ai-overview"
    endpoint: Literal["google_ai_overview"] = "google_ai_overview"


class GoogleAiMode(_GoogleLocale, _GoogleOrigin):
    """GET /api/google/ai-mode"""

    path: ClassVar[str] = "/api/google/ai-mode"
    endpoint: Literal["google_ai_mode"] = "google_ai_mode"
    q: str
    device: Device | None = None
    continuable: bool | None = None
    subsequent_request_token: str | None = None
    image_url: str | None = None

    @model_validator(mode="after")
    def _check_ai_mode(self) -> GoogleAiMode:
        _at_most_one(self, "image_url", "subsequent_request_token")
        return self


class GoogleAds(ScrapeRequest):
    """GET /api/google/ads"""

    path: ClassVar[str] = "/api/google/ads"
    endpoint: Literal["google_ads"] = "google_ads"
    q: str
    location: str
    hl: str | None = None
    safe: Literal["active", "off"] | None = None
    nfpr: Flag | None = None
    device: Device | None = None


class GoogleShopping(_GoogleLocale, _GoogleOrigin):
    """GET /api/google/shopping"""

    path: ClassVar[str] = "/api/google/shopping"
    endpoint: Literal["google_shopping"] = "google_shopping"
    q: str | None = None
    shoprs: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    sort_by: Annotated[Literal["1", "2", "3", "4"], BeforeValidator(_stringify)] | None = None
    free_shipping: bool | None = None
    on_sale: bool | None = None
    small_business: bool | None = None
    start: int | None = None
    num: int | None = None
    device: Device | None = None

    @model_validator(mode="after")
    def _check_shopping(self) -> GoogleShopping:
        _require_any(self, "q", "shoprs")
        refinements = [
            self.min_price is not None or self.max_price is not None,
            bool(self.on_sale),
            bool(self.free_shipping),
            bool(self.small_business),
        ]
        if sum(refinements) > 1:
            raise ValueError(
                "only one of a price range, on_sale, free_shipping, or small_business may be used"
            )
        return self


class GoogleShoppingProduct(_GoogleLocale, _GoogleOrigin):
    """GET /api/google/shopping/product"""

    path: ClassVar[str] = "/api/google/shopping/product"
    endpoint: Literal["google_shopping_product"] = "google_shopping_product"
    q: str
    gpcid: str | None = None
    headline_offer_docid: str | None = None
    image_docid: str | None = None
    prds: str | None = None
    device: Device | None = None

    @model_validator(mode="after")
    def _check_product(self) -> GoogleShoppingProduct:
        _exactly_one(self, "gpcid", "prds")
        _requires(self, "headline_offer_docid", "gpcid")
        _requires(self, "image_docid", "gpcid")
        return self


class GoogleLocal(_GoogleLocale, _GoogleOrigin):
    """GET /api/google/local"""

    path: ClassVar[str] = "/api/google/local"
    endpoint: Literal["google_local"] = "google_local"
    q: str
    ludocid: str | None = None
    tbs: str | None = None
    start: int | None = None
    device: Device | None = None


class GoogleMaps(_GoogleLocale):
    """GET /api/google/maps"""

    path: ClassVar[str] = "/api/google/maps"
    endpoint: Literal["google_maps"] = "google_maps"
    q: str | None = None
    ll: str | None = None
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    z: float | None = None
    m: int | None = None
    nearby: bool | None = None
    data: str | None = None
    place_id: str | None = None
    data_cid: str | None = None
    type: Literal["search", "place"] | None = None
    start: int | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_rating: float | None = None
    open_state: Literal["now", "24h"] | None = None
    open_on_day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] | None = None
    open_at_hour: int | None = None

    @model_validator(mode="after")
    def _check_maps(self) -> GoogleMaps:
        _require_any(self, "q", "place_id", "data_cid", "data")
        _at_most_one(self, "place_id", "data_cid", "data")
        if not _present(self, "place_id", "data_cid", "data") and self.type is None:
            raise ValueError("type is required when searching by q")
        if self.type == "search" and self.q is None:
            raise ValueError("q is required when type=search")
        _paired(self, "lat", "lon")
        _at_most_one(self, "ll", "lat", "location")
        _at_most_one(self, "z", "m")
        _at_most_one(self, "open_state", "open_on_day")
        _at_most_one(self, "open_state", "open_at_hour")
        _requires(self, "open_at_hour", "open_on_day")
        return self


class GoogleMapsLiveFootTraffic(_GoogleLocale):
    """GET /api/google/maps/popular-times"""

    path: ClassVar[str] = "/api/google/maps/popular-times"
    endpoint: Literal["google_maps_live_foot_traffic"] = "google_maps_live_foot_traffic"
    place_id: str


class GoogleMapsPosts(_GoogleLocale):
    """GET /api/google/maps/posts"""

    path: ClassVar[str] = "/api/google/maps/posts"
    endpoint: Literal["google_maps_posts"] = "google_maps_posts"
    data_id: str
    next_page_token: str | None = None


class GoogleMapsPhoto(_GoogleLocale):
    """GET /api/google/maps/photo-meta"""

    path: ClassVar[str] = "/api/google/maps/photo-meta"
    endpoint: Literal["google_maps_photo"] = "google_maps_photo"
    data_id: str


class GoogleMapsWebResults(_GoogleLocale):
    """GET /api/google/maps/web"""

    path: ClassVar[str] = "/api/google/maps/web"
    endpoint: Literal["google_maps_web_results"] = "google_maps_web_results"
    q: str
    ibp: str
    device: Literal["desktop"] | None = None
    start: int | None = None


class GoogleReviews(ScrapeRequest):
    """GET /api/google/reviews"""

    path: ClassVar[str] = "/api/google/reviews"
    endpoint: Literal["google_reviews"] = "google_reviews"
    place_id: str | None = None
    data_id: str | None = None
    hl: str | None = None
    gl: str | None = None
    sort_by: Literal["qualityScore", "newestFirst", "ratingHigh", "ratingLow"] | None = None
    topic_id: str | None = None
    query: str | None = None
    num: int | None = None
    next_page_token: str | None = None
    source_metadata: bool | None = None

    @model_validator(mode="after")
    def _check_reviews(self) -> GoogleReviews:
        _exactly_one(self, "place_id", "data_id")
        _at_most_one(self, "topic_id", "query")
        return self


class GoogleContributorReviews(ScrapeRequest):
    """GET /api/google/contributor-reviews"""

    path: ClassVar[str] = "/api/google/contributor-reviews"
    endpoint: Literal["google_contributor_reviews"] = "google_contributor_reviews"
    contributor_id: str
    hl: str | None = None
    gl: str | None = None
    limit: int | None = None


class BingSearch(ScrapeRequest):
    """GET /api/bing/search"""

    path: ClassVar[str] = "/api/bing/search"
    endpoint: Literal["bing_search"] = "bing_search"
    engine: Literal["bing"] | None = None
    q: str
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    mkt: str | None = None
    cc: str | None = None
    first: int | None = None
    safeSearch: Literal["off", "moderate", "strict"] | None = None
    filters: str | None = None
    device: Device | None = None

    @model_validator(mode="after")
    def _check_bing(self) -> BingSearch:
        _at_most_one(self, "mkt", "cc")
        return self


class BingMaps(ScrapeRequest):
    """GET /api/bing/maps"""

    path: ClassVar[str] = "/api/bing/maps"
    endpoint: Literal["bing_maps"] = "bing_maps"
    q: str | None = None
    place_id: str | None = None
    cp: str | None = None
    setlang: str | None = None
    first: int | None = None
    count: int | None = None

    @model_validator(mode="after")
    def _check_bing_maps(self) -> BingMaps:
        _require_any(self, "q", "place_id")
        return self


class DuckDuckGoSearch(ScrapeRequest):
    """GET /api/duckduckgo/search"""

    path: ClassVar[str] = "/api/duckduckgo/search"
    endpoint: Literal["duckduckgo_search"] = "duckduckgo_search"
    q: str
    kl: str | None = None
    search_assist: bool | None = None
    safe: Annotated[Literal["1", "-1", "-2"], BeforeValidator(_stringify)] | None = None
    df: str | None = None
    start: int | None = None
    m: int | None = None

    @model_validator(mode="after")
    def _check_duckduckgo(self) -> DuckDuckGoSearch:
        _at_most_one(self, "m", "search_assist")
        return self


class DuckDuckGoMaps(ScrapeRequest):
    """GET /api/duckduckgo/maps"""

    path: ClassVar[str] = "/api/duckduckgo/maps"
    endpoint: Literal["duckduckgo_maps"] = "duckduckgo_maps"
    q: str
    bbox: str | None = None
    lat: float | None = None
    lon: float | None = None
    strict_bbox: bool | None = None

    @model_validator(mode="after")
    def _check_duckduckgo_maps(self) -> DuckDuckGoMaps:
        _paired(self, "lat", "lon")
        _exactly_one(self, "bbox", "lat")
        return self


class YelpSearch(ScrapeRequest):
    """GET /api/yelp/search"""

    path: ClassVar[str] = "/api/yelp/search"
    endpoint: Literal["yelp_search"] = "yelp_search"
    find_desc: str | None = None
    find_loc: str
    yelp_domain: str | None = None
    l: str | None = None  # noqa: E741 - Yelp's own parameter name
    cflt: str | None = None
    sortby: Literal["recommended", "rating", "review_count"] | None = None
    attrs: str | None = None
    start: int | None = None


class YelpReviews(ScrapeRequest):
    """GET /api/yelp/reviews (q, not_recommended, and not_recommended_start are refused by the API)"""

    path: ClassVar[str] = "/api/yelp/reviews"
    endpoint: Literal["yelp_reviews"] = "yelp_reviews"
    place_id: str
    yelp_domain: str | None = None
    hl: str | None = None
    q: str | None = None
    sortby: (
        Literal["relevance_desc", "date_desc", "date_asc", "rating_desc", "rating_asc", "elites_desc"] | None
    ) = None
    rating: str | None = None
    not_recommended: bool | None = None
    start: int | None = None
    num: int | None = None
    not_recommended_start: int | None = None


class TripadvisorSearch(ScrapeRequest):
    """GET /api/tripadvisor/search"""

    path: ClassVar[str] = "/api/tripadvisor/search"
    endpoint: Literal["tripadvisor_search"] = "tripadvisor_search"
    q: str
    tripadvisor_domain: str | None = None
    locale: str | None = None
    geo_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    place_type: (
        Literal["all", "accommodation", "attraction", "attraction_product", "eatery", "geo"] | None
    ) = None
    start: int | None = None
    num: int | None = None

    @model_validator(mode="after")
    def _check_tripadvisor(self) -> TripadvisorSearch:
        _paired(self, "lat", "lon")
        return self


class TripadvisorPlace(ScrapeRequest):
    """GET /api/tripadvisor/place"""

    path: ClassVar[str] = "/api/tripadvisor/place"
    endpoint: Literal["tripadvisor_place"] = "tripadvisor_place"
    place_id: str
    tripadvisor_domain: str | None = None
    locale: str | None = None
    currency: str | None = None
    geo_id: int | None = None


class TripadvisorReviews(ScrapeRequest):
    """GET /api/tripadvisor/reviews"""

    path: ClassVar[str] = "/api/tripadvisor/reviews"
    endpoint: Literal["tripadvisor_reviews"] = "tripadvisor_reviews"
    place_id: str
    tripadvisor_domain: str | None = None
    locale: str | None = None
    start: int | None = None
    num: int | None = None
    sort_by: Literal["recent", "relevance"] | None = None
    translate: bool | None = None


class AppleMapsPlaces(ScrapeRequest):
    """GET /api/apple/maps/places (muid: one to fifty comma-separated IDs)"""

    path: ClassVar[str] = "/api/apple/maps/places"
    endpoint: Literal["apple_maps_places"] = "apple_maps_places"
    muid: str
    locale: str | None = None


class AppleMapsReviews(ScrapeRequest):
    """GET /api/apple/maps/reviews (muid: exactly one ID)"""

    path: ClassVar[str] = "/api/apple/maps/reviews"
    endpoint: Literal["apple_maps_reviews"] = "apple_maps_reviews"
    muid: str
    locale: str | None = None


class GooglePlayApps(ScrapeRequest, PlayAppsRequest):
    """Alpha. GET /api/google/play/apps. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/apps"
    endpoint: Literal["google_play_apps"] = "google_play_apps"


class GooglePlayGames(ScrapeRequest, PlayGamesRequest):
    """Alpha. GET /api/google/play/games. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/games"
    endpoint: Literal["google_play_games"] = "google_play_games"


class GooglePlayBooks(ScrapeRequest, PlayBooksRequest):
    """Alpha. GET /api/google/play/books. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/books"
    endpoint: Literal["google_play_books"] = "google_play_books"


class GooglePlayMovies(ScrapeRequest, PlayMoviesRequest):
    """Alpha. GET /api/google/play/movies. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/movies"
    endpoint: Literal["google_play_movies"] = "google_play_movies"


class GooglePlayProduct(ScrapeRequest, PlayProductRequest):
    """Alpha. GET /api/google/play/product. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/product"
    endpoint: Literal["google_play_product"] = "google_play_product"


class GooglePlayReviews(ScrapeRequest, PlayReviewsRequest):
    """Alpha. GET /api/google/play/reviews. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/reviews"
    endpoint: Literal["google_play_reviews"] = "google_play_reviews"


class AppleAppStoreSearch(ScrapeRequest, AppleSearchRequest):
    """Alpha. GET /api/apple/app-store/search. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/apple/app-store/search"
    endpoint: Literal["apple_app_store_search"] = "apple_app_store_search"


class AppleAppStoreProduct(ScrapeRequest, AppleProductRequest):
    """Alpha. GET /api/apple/app-store/product. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/apple/app-store/product"
    endpoint: Literal["apple_app_store_product"] = "apple_app_store_product"


class AppleAppStoreReviews(ScrapeRequest, AppleReviewsRequest):
    """Alpha. GET /api/apple/app-store/reviews. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/apple/app-store/reviews"
    endpoint: Literal["apple_app_store_reviews"] = "apple_app_store_reviews"


Selector = Annotated[str, Field(min_length=1, max_length=2048)]


class WebFetch(ScrapeRequest):
    """Alpha. GET /api/web/fetch: a public page as Markdown, HTML, text, or a base64 PNG screenshot."""

    path: ClassVar[str] = "/api/web/fetch"
    endpoint: Literal["web_fetch"] = "web_fetch"
    url: Annotated[str, Field(min_length=1, max_length=8192)]
    respond_with: Literal["markdown", "html", "text", "screenshot"] | None = None
    target_selector: Selector | None = None
    remove_selector: Selector | None = None
    wait_for_selector: Selector | None = None
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None = None
    page_timeout: Annotated[int, Field(ge=1, le=180)] | None = None
    locale: Annotated[str, Field(min_length=2, max_length=64)] | None = None
    user_agent: Annotated[str, Field(min_length=1, max_length=1024)] | None = None
    with_links: Literal["inlined", "referenced", "collapsed", "shortcut", "discarded"] | None = None
    with_images: Literal["all", "alt", "none"] | None = None
    with_iframe: StrictBool | Literal["true", "false", "quoted"] | None = None
    with_shadow_dom: StrictBool | Literal["true", "false"] | None = None


_REQUEST_CLASSES: tuple[type[ScrapeRequest], ...] = (
    GoogleSearch,
    GoogleAiOverview,
    GoogleAiMode,
    GoogleAds,
    GoogleShopping,
    GoogleShoppingProduct,
    GoogleLocal,
    GoogleMaps,
    GoogleMapsLiveFootTraffic,
    GoogleMapsPosts,
    GoogleMapsPhoto,
    GoogleMapsWebResults,
    GoogleReviews,
    GoogleContributorReviews,
    BingSearch,
    BingMaps,
    DuckDuckGoSearch,
    DuckDuckGoMaps,
    YelpSearch,
    YelpReviews,
    TripadvisorSearch,
    TripadvisorPlace,
    TripadvisorReviews,
    AppleMapsPlaces,
    AppleMapsReviews,
    GooglePlayApps,
    GooglePlayGames,
    GooglePlayBooks,
    GooglePlayMovies,
    GooglePlayProduct,
    GooglePlayReviews,
    AppleAppStoreSearch,
    AppleAppStoreProduct,
    AppleAppStoreReviews,
    WebFetch,
)

AnyRequest = Annotated[
    GoogleSearch
    | GoogleAiOverview
    | GoogleAiMode
    | GoogleAds
    | GoogleShopping
    | GoogleShoppingProduct
    | GoogleLocal
    | GoogleMaps
    | GoogleMapsLiveFootTraffic
    | GoogleMapsPosts
    | GoogleMapsPhoto
    | GoogleMapsWebResults
    | GoogleReviews
    | GoogleContributorReviews
    | BingSearch
    | BingMaps
    | DuckDuckGoSearch
    | DuckDuckGoMaps
    | YelpSearch
    | YelpReviews
    | TripadvisorSearch
    | TripadvisorPlace
    | TripadvisorReviews
    | AppleMapsPlaces
    | AppleMapsReviews
    | GooglePlayApps
    | GooglePlayGames
    | GooglePlayBooks
    | GooglePlayMovies
    | GooglePlayProduct
    | GooglePlayReviews
    | AppleAppStoreSearch
    | AppleAppStoreProduct
    | AppleAppStoreReviews
    | WebFetch,
    Field(discriminator="endpoint"),
]

REQUEST_ADAPTER: TypeAdapter[ScrapeRequest] = TypeAdapter(AnyRequest)
REQUEST_TYPES: dict[str, type[ScrapeRequest]] = {
    cls.model_fields["endpoint"].default: cls for cls in _REQUEST_CLASSES
}


class KeyStatus(BaseModel):
    """Balance and limits of an API key, as returned by GET /api/keys/status."""

    model_config = ConfigDict(extra="allow")
    remaining_calls: int
    concurrency_limit: int | None = None
    status: str = ""
    free_calls: int | None = None
    minimum_top_up_cents: int | None = None
    cents_per_1000_calls: int | None = None
    has_billing_email: bool | None = None
    credit_expiry_months: int | None = None
    credits_expire_at: str | None = None
    expiring_calls: int | None = None
    request_id: str = ""
