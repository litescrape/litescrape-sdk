"""Request models: one class per endpoint, joined by the ``endpoint`` discriminator."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    TypeAdapter,
    field_validator,
    model_validator,
)

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
    if isinstance(value, list | tuple | dict):
        return json.dumps(value, separators=(",", ":"))
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


def _as_int(value: Any) -> Any:
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value)
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


def _ordered(model: BaseModel, low: str, high: str) -> None:
    minimum, maximum = getattr(model, low), getattr(model, high)
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"{high} must be at least {low}")


def _requires_later_page(model: Any) -> None:
    if model.page_token is not None and (model.page or 1) == 1:
        raise ValueError("page_token requires page greater than 1")


def _alone(model: BaseModel, name: str) -> None:
    others = sorted(
        field
        for field in model.model_fields_set - {name, "endpoint", "timeout"}
        if getattr(model, field) is not None
    )
    if getattr(model, name) is not None and others:
        raise ValueError(f"{name} must be sent alone, without {', '.join(others)}")


Flag = Annotated[Literal["0", "1"], BeforeValidator(_flag)]
Device = Literal["desktop", "tablet", "mobile"]
SafeSearch = Literal["off", "moderate", "strict"]
TimeoutSeconds = Annotated[float, Field(gt=0, le=90, allow_inf_nan=False, strict=True)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
JobText = Annotated[str, Field(min_length=1, max_length=512)]
JobPageToken = Annotated[str, Field(min_length=1, max_length=32768, pattern=r"^[A-Za-z0-9+/=_-]+$")]
JobKeys = Annotated[list[JobText], Field(min_length=1, max_length=100)]
LevelsSlug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,127}$")]
Asin = Annotated[str, Field(pattern=r"^[A-Z0-9]{10}$")]
AmazonDomain = Literal[
    "amazon.ae",
    "amazon.ca",
    "amazon.co.jp",
    "amazon.co.uk",
    "amazon.co.za",
    "amazon.com",
    "amazon.com.au",
    "amazon.com.be",
    "amazon.com.br",
    "amazon.com.mx",
    "amazon.com.tr",
    "amazon.de",
    "amazon.eg",
    "amazon.es",
    "amazon.fr",
    "amazon.ie",
    "amazon.in",
    "amazon.it",
    "amazon.nl",
    "amazon.pl",
    "amazon.sa",
    "amazon.se",
    "amazon.sg",
]
EbayDomain = Literal[
    "ebay.com",
    "ebay.co.uk",
    "ebay.ca",
    "ebay.com.au",
    "ebay.de",
    "ebay.fr",
    "ebay.it",
    "ebay.es",
    "ebay.at",
    "ebay.be",
    "ebay.ch",
    "ebay.ie",
    "ebay.nl",
    "ebay.com.hk",
    "ebay.com.my",
    "ebay.pl",
    "ebay.com.sg",
]
YandexDomain = Literal["yandex.com", "yandex.ru", "yandex.by", "yandex.kz", "yandex.uz", "yandex.com.tr"]
XUsername = Annotated[str, Field(pattern=r"^[A-Za-z0-9_]{1,15}$")]
XId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
TikTokHandle = Annotated[str, Field(pattern=r"^@?[A-Za-z0-9_.]{1,24}$")]
TikTokCount = Annotated[int, Field(ge=1, le=35)]
NumericId = Annotated[str, Field(pattern=r"^[0-9]{1,25}$")]
InstagramHandle = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.]{1,30}$")]
FacebookQuery = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S(?:.*\S)?$")]
RetailQuery = Annotated[str, Field(min_length=1, max_length=500)]
ProductUrl = Annotated[str, Field(min_length=1, max_length=4096)]
StoreId = Annotated[str, Field(min_length=1, max_length=8, pattern=r"^[0-9]{1,8}$")]
Selector = Annotated[str, Field(min_length=1, max_length=2048)]
Cookie = Annotated[str, Field(min_length=3, max_length=4096)]
Selectors = Selector | Annotated[list[Selector], Field(min_length=1, max_length=16)]
Scripts = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=8192)]], Field(min_length=1, max_length=8)
]
RespondTiming = Literal[
    "html", "visible-content", "mutation-idle", "resource-idle", "media-idle", "network-idle"
]
FETCH_FORMATS = ("content", "markdown", "html", "text", "frontmatter")


class MerchantProduct(BaseModel):
    """One headline offer for ``GoogleShoppingMerchantUrls``, copied from a Shopping result."""

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)
    gpcid: Annotated[str, Field(pattern=r"^[0-9]{1,20}$")] | None = None
    headline_offer_docid: Annotated[str, Field(pattern=r"^[0-9]{1,20}$")]
    merchant: Annotated[str, Field(min_length=1, max_length=200)]


class ChatMessage(BaseModel):
    """One text message for ``CopilotChatCompletions``."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: Annotated[str, Field(min_length=1, max_length=32000)]

    @model_validator(mode="after")
    def _check_content(self) -> ChatMessage:
        if not self.content.strip():
            raise ValueError("content must not be blank")
        return self


class Viewport(BaseModel):
    """Browser viewport for ``WebFetch`` and ``WebScreenshot``; width and height are required."""

    model_config = ConfigDict(extra="forbid")
    width: Annotated[int, Field(ge=1, le=4096)]
    height: Annotated[int, Field(ge=1, le=4096)]
    device_scale_factor: Annotated[float, Field(gt=0, le=4)] | None = None
    is_mobile: bool | None = None
    is_landscape: bool | None = None
    has_touch: bool | None = None


class MarkdownOptions(BaseModel):
    """Markdown formatting options for ``WebFetch``."""

    model_config = ConfigDict(extra="forbid")
    heading_style: Literal["setext", "atx"] | None = None
    hr: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    bullet_list_marker: Literal["-", "+", "*"] | None = None
    em_delimiter: Literal["_", "*"] | None = None
    strong_delimiter: Literal["__", "**"] | None = None
    link_style: Literal["inlined", "referenced", "discarded"] | None = None
    link_reference_style: Literal["full", "collapsed", "shortcut", "discarded"] | None = None


class ScrapeRequest(BaseModel):
    """Base of every endpoint request. Subclasses set ``path`` and the ``endpoint`` literal.

    ``method`` is ``GET`` for endpoints that take query parameters and ``POST`` for endpoints whose
    requests carry arrays or nested objects, which are sent as a JSON body (see ``body``).
    """

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True, populate_by_name=True)
    path: ClassVar[str]
    method: ClassVar[str] = "GET"
    timeout: TimeoutSeconds | None = None

    def query_params(self) -> dict[str, str]:
        dumped = self.model_dump(exclude_none=True, exclude={"endpoint"}, by_alias=True)
        return {name: _as_query(value) for name, value in dumped.items()}

    def body(self) -> dict[str, Any]:
        """The request as a JSON object with native types, as sent by ``POST`` endpoints."""
        return self.model_dump(mode="json", exclude_none=True, exclude={"endpoint"}, by_alias=True)


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
        if getattr(self, "page_token", None) is not None:
            _alone(self, "page_token")
            return self
        _require_any(self, "q", "ludocid", "kgmid")
        _paired(self, "lat", "lon")
        _at_most_one(self, "location", "uule", "lat")
        _paired(self, "as_nlo", "as_nhi")
        _requires(self, "as_dt", "as_sitesearch")
        return self


class GoogleSearch(_GoogleSearchFields):
    """GET /api/google/search

    ``page_token`` (from ``pagination.next_page_token``) fetches the next page and must be sent alone.
    """

    path: ClassVar[str] = "/api/google/search"
    endpoint: Literal["google_search"] = "google_search"
    fast_mode: StrictBool | Literal["true", "false"] | None = None
    page_token: Annotated[str, Field(max_length=32768)] | None = None


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


class GoogleGemini(ScrapeRequest):
    """GET /api/google/gemini"""

    path: ClassVar[str] = "/api/google/gemini"
    endpoint: Literal["google_gemini"] = "google_gemini"
    prompt: Annotated[str, Field(min_length=1, max_length=32000)]
    hl: Annotated[str, Field(pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z]{2,4})?$")] | None = None
    continuable: bool | None = None
    subsequent_request_token: Annotated[str, Field(min_length=1, max_length=32768)] | None = None


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


class GoogleShoppingMerchantUrls(ScrapeRequest):
    """POST /api/google/shopping/merchant-urls: merchant URLs for 1 to 100 Shopping offers, as a JSON body."""

    path: ClassVar[str] = "/api/google/shopping/merchant-urls"
    endpoint: Literal["google_shopping_merchant_urls"] = "google_shopping_merchant_urls"
    method: ClassVar[str] = "POST"
    products: Annotated[list[MerchantProduct], Field(min_length=1, max_length=100)]
    gl: Annotated[str, Field(pattern=r"^[a-zA-Z]{2}$")] | None = None
    hl: Annotated[str, Field(pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z]{2,4})?$")] | None = None


class GoogleLocal(_GoogleLocale, _GoogleOrigin):
    """GET /api/google/local"""

    path: ClassVar[str] = "/api/google/local"
    endpoint: Literal["google_local"] = "google_local"
    q: str
    ludocid: str | None = None
    tbs: str | None = None
    start: int | None = None
    device: Device | None = None


class GoogleImages(ScrapeRequest):
    """GET /api/google/images"""

    path: ClassVar[str] = "/api/google/images"
    endpoint: Literal["google_images"] = "google_images"
    q: Annotated[str, Field(min_length=1, max_length=2048)]
    hl: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Za-z]{2,8})?$")] | None = None
    gl: Annotated[str, Field(pattern=r"^[a-z]{2}$")] | None = None
    safe: Literal["active", "off"] | None = None
    tbs: Annotated[str, Field(max_length=4096)] | None = None
    start: Annotated[int, Field(ge=0, le=1000)] | None = None
    num: Annotated[int, Field(ge=1, le=100)] | None = None
    device: Device | None = None


class GoogleJobs(ScrapeRequest):
    """GET /api/google/jobs"""

    path: ClassVar[str] = "/api/google/jobs"
    endpoint: Literal["google_jobs"] = "google_jobs"
    q: JobText
    page: Annotated[int, Field(ge=1)] | None = None
    page_token: JobPageToken | None = None
    hl: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Za-z]{2,8})?$")] | None = None
    gl: Annotated[str, Field(pattern=r"^[a-z]{2}$")] | None = None
    location: JobText | None = None
    uule: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    lat: Latitude | None = None
    lon: Longitude | None = None
    radius: Annotated[float, Field(ge=1, le=199)] | None = None
    uds: Annotated[str, Field(min_length=1, max_length=16384)] | None = None
    tbs: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    include_filters: bool | None = None

    @model_validator(mode="after")
    def _check_jobs(self) -> GoogleJobs:
        _requires_later_page(self)
        _paired(self, "lat", "lon")
        _at_most_one(self, "location", "uule", "lat")
        _requires(self, "radius", "lat")
        return self


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


class BingImages(ScrapeRequest):
    """GET /api/bing/images"""

    path: ClassVar[str] = "/api/bing/images"
    endpoint: Literal["bing_images"] = "bing_images"
    q: Annotated[str, Field(min_length=1, max_length=2048)]
    first: Annotated[int, Field(ge=1, le=10000)] | None = None
    count: Annotated[int, Field(ge=1, le=100)] | None = None
    mkt: Annotated[str, Field(pattern=r"^[a-zA-Z]{2}-[a-zA-Z]{2}$")] | None = None
    cc: Annotated[str, Field(pattern=r"^[a-zA-Z]{2}$")] | None = None
    safeSearch: SafeSearch | None = None
    imagesize: Literal["small", "medium", "large", "wallpaper"] | None = None
    photo: Literal["photo", "clipart", "linedrawing", "animatedgif", "transparent"] | None = None
    aspect: Literal["square", "wide", "tall"] | None = None
    color2: (
        Literal[
            "color",
            "bw",
            "FGcls_RED",
            "FGcls_ORANGE",
            "FGcls_YELLOW",
            "FGcls_GREEN",
            "FGcls_TEAL",
            "FGcls_BLUE",
            "FGcls_PURPLE",
            "FGcls_PINK",
            "FGcls_BROWN",
            "FGcls_BLACK",
            "FGcls_GRAY",
            "FGcls_WHITE",
        ]
        | None
    ) = None
    face: Literal["face", "portrait"] | None = None
    age: Literal["lt1440", "lt10080", "lt43200", "lt525600"] | None = None
    license: (
        Literal[
            "L1",
            "L2",
            "L3",
            "L4",
            "L5",
            "L6",
            "L7",
            "L2_L3",
            "L2_L3_L4",
            "L2_L3_L5_L6",
            "L2_L3_L4_L5_L6_L7",
            "creativecommons",
        ]
        | None
    ) = None
    qft: Annotated[str, Field(max_length=2048)] | None = None

    @model_validator(mode="after")
    def _check_bing_images(self) -> BingImages:
        _at_most_one(self, "mkt", "cc")
        return self


class BingShopping(ScrapeRequest):
    """GET /api/bing/shopping"""

    path: ClassVar[str] = "/api/bing/shopping"
    endpoint: Literal["bing_shopping"] = "bing_shopping"
    q: Annotated[str, Field(min_length=1, max_length=2048)]
    mkt: Annotated[str, Field(pattern=r"^[A-Za-z]{2}-[A-Za-z]{2}$")] | None = None
    cc: Annotated[str, Field(pattern=r"^[A-Za-z]{2}$")] | None = None
    efirst: Annotated[int, Field(ge=0)] | None = None
    filters: Annotated[str, Field(max_length=6000)] | None = None

    @model_validator(mode="after")
    def _check_bing_shopping(self) -> BingShopping:
        _at_most_one(self, "mkt", "cc")
        return self


class BingProduct(ScrapeRequest):
    """GET /api/bing/product"""

    path: ClassVar[str] = "/api/bing/product"
    endpoint: Literal["bing_product"] = "bing_product"
    product_token: Annotated[str, Field(min_length=1, max_length=24000)]


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
    """GET /api/yelp/reviews"""

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

    @model_validator(mode="after")
    def _check_yelp_reviews(self) -> YelpReviews:
        if self.not_recommended_start is not None and not self.not_recommended:
            raise ValueError("not_recommended_start requires not_recommended=true")
        return self


class YelpPlace(ScrapeRequest):
    """GET /api/yelp/place"""

    path: ClassVar[str] = "/api/yelp/place"
    endpoint: Literal["yelp_place"] = "yelp_place"
    place_id: str
    yelp_domain: str | None = None
    business_alert: bool | None = None
    full_menu: bool | None = None
    menu_name: str | None = None

    @model_validator(mode="after")
    def _check_yelp_place(self) -> YelpPlace:
        if self.menu_name is not None and not self.full_menu:
            raise ValueError("menu_name requires full_menu=true")
        return self


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
    """GET /api/google/play/apps. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/apps"
    endpoint: Literal["google_play_apps"] = "google_play_apps"


class GooglePlayGames(ScrapeRequest, PlayGamesRequest):
    """GET /api/google/play/games. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/games"
    endpoint: Literal["google_play_games"] = "google_play_games"


class GooglePlayBooks(ScrapeRequest, PlayBooksRequest):
    """GET /api/google/play/books. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/books"
    endpoint: Literal["google_play_books"] = "google_play_books"


class GooglePlayMovies(ScrapeRequest, PlayMoviesRequest):
    """GET /api/google/play/movies. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/movies"
    endpoint: Literal["google_play_movies"] = "google_play_movies"


class GooglePlayProduct(ScrapeRequest, PlayProductRequest):
    """GET /api/google/play/product. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/product"
    endpoint: Literal["google_play_product"] = "google_play_product"


class GooglePlayReviews(ScrapeRequest, PlayReviewsRequest):
    """GET /api/google/play/reviews. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/google/play/reviews"
    endpoint: Literal["google_play_reviews"] = "google_play_reviews"


class AppleAppStoreSearch(ScrapeRequest, AppleSearchRequest):
    """GET /api/apple/app-store/search. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/apple/app-store/search"
    endpoint: Literal["apple_app_store_search"] = "apple_app_store_search"


class AppleAppStoreProduct(ScrapeRequest, AppleProductRequest):
    """GET /api/apple/app-store/product. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/apple/app-store/product"
    endpoint: Literal["apple_app_store_product"] = "apple_app_store_product"


class AppleAppStoreReviews(ScrapeRequest, AppleReviewsRequest):
    """GET /api/apple/app-store/reviews. See the Store API reference for field availability."""

    path: ClassVar[str] = "/api/apple/app-store/reviews"
    endpoint: Literal["apple_app_store_reviews"] = "apple_app_store_reviews"


class _BrowserRequest(ScrapeRequest):
    method: ClassVar[str] = "POST"
    url: Annotated[str, Field(min_length=1, max_length=8192)]
    remove_overlay: bool | None = None
    detach_invisibles: bool | None = None
    wait_for_selector: Selectors | None = None
    set_cookies: Annotated[list[Cookie], Field(min_length=1, max_length=100)] | None = None
    user_agent: Annotated[str, Field(min_length=1, max_length=1024)] | None = None
    inject_page_script: Scripts | None = None
    inject_frame_script: Scripts | None = None
    page_timeout: Annotated[int, Field(ge=1, le=180)] | None = None
    locale: (
        Annotated[str, Field(min_length=2, max_length=64, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")]
        | None
    ) = None
    referer: Annotated[str, Field(min_length=1, max_length=8192)] | None = None
    assert_status_code: Annotated[int, Field(ge=100, le=599)] | None = None
    viewport: Viewport | None = None
    robots_txt: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    respond_timing: RespondTiming | None = None


class WebFetch(_BrowserRequest):
    """Alpha. POST /api/web/fetch: a public page as Markdown, HTML, or text, sent as a JSON body.

    ``respond_with`` is one of ``content`` (the default), ``markdown``, ``html``, ``text`` and
    ``frontmatter``, or a ``+`` combination such as ``markdown+frontmatter``. Screenshots moved to
    ``WebScreenshot``.
    """

    path: ClassVar[str] = "/api/web/fetch"
    endpoint: Literal["web_fetch"] = "web_fetch"
    respond_with: Annotated[str, Field(min_length=3, max_length=64)] | None = None
    with_links_summary: bool | Literal["all"] | None = None
    with_images_summary: bool | None = None
    retain_images: Literal["none", "all", "alt"] | None = None
    retain_links: Literal["none", "all", "text", "gpt-oss"] | None = None
    retain_media: Literal["none", "text", "link", "image", "html"] | None = None
    preset: Literal["reader", "index", "research", "agent", "spider"] | None = None
    no_gfm: bool | Literal["table"] | None = None
    target_selector: Selectors | None = None
    remove_selector: Selectors | None = None
    keep_img_data_url: bool | None = None
    with_iframe: bool | Literal["quoted"] | None = None
    with_shadow_dom: bool | None = None
    engine: Literal["auto", "browser", "curl"] | None = None
    token_budget: Annotated[int, Field(ge=1, le=10000000)] | None = None
    markdown: MarkdownOptions | None = None
    markdown_chunking: (
        Literal["true", "h1", "h2", "h3", "h4", "h5", "structured", "s1", "s2", "s3", "s4", "s5"] | None
    ) = None
    max_tokens: Annotated[int, Field(ge=500, le=10000000)] | None = None
    base: Literal["initial", "final"] | None = None

    @field_validator("respond_with")
    @classmethod
    def _check_respond_with(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = value.lower().split("+")
        if any(part not in FETCH_FORMATS for part in parts) or len(set(parts)) != len(parts):
            raise ValueError(
                f"respond_with must be one of, or a '+' combination of: {', '.join(FETCH_FORMATS)}"
            )
        return "+".join(parts)


class WebScreenshot(_BrowserRequest):
    """Alpha. POST /api/web/screenshot: a public page as a base64 PNG, sent as a JSON body."""

    path: ClassVar[str] = "/api/web/screenshot"
    endpoint: Literal["web_screenshot"] = "web_screenshot"
    full_page: bool | None = None


class BraveSearch(ScrapeRequest):
    """GET /api/brave/search"""

    path: ClassVar[str] = "/api/brave/search"
    endpoint: Literal["brave_search"] = "brave_search"
    q: Annotated[str, Field(min_length=1, max_length=2048)]
    offset: Annotated[int, Field(ge=0, le=9)] | None = None
    country: Annotated[str, Field(pattern=r"^(?:[a-z]{2}|all)$")] | None = None
    ui_lang: Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[a-z]{2})?$")] | None = None
    safesearch: SafeSearch | None = None
    tf: Literal["pd", "pw", "pm", "py"] | None = None
    spellcheck: bool | None = None


class BraveAiMode(ScrapeRequest):
    """GET /api/brave/ai-mode"""

    path: ClassVar[str] = "/api/brave/ai-mode"
    endpoint: Literal["brave_ai_mode"] = "brave_ai_mode"
    location: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    lat: Latitude | None = None
    lon: Longitude | None = None
    country: Annotated[str, Field(pattern=r"^(?:[a-z]{2}|all)$")] | None = None
    language: Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[a-z]{2})?$")] | None = None
    safeSearch: SafeSearch | None = None
    units_of_measurement: Literal["us", "metric"] | None = None
    q: Annotated[str, Field(min_length=1, max_length=2048)]
    continuation_token: (
        Annotated[str, Field(min_length=1, max_length=4096, pattern=r"^ct2_[A-Za-z0-9_-]{100,}$")] | None
    ) = None

    @model_validator(mode="after")
    def _check_brave_ai_mode(self) -> BraveAiMode:
        _paired(self, "lat", "lon")
        return self


class BaiduSearch(ScrapeRequest):
    """GET /api/baidu/search"""

    path: ClassVar[str] = "/api/baidu/search"
    endpoint: Literal["baidu_search"] = "baidu_search"
    q: Annotated[str, Field(min_length=1, max_length=500)]
    pn: Annotated[int, Field(ge=0, le=750)] | None = None
    rn: Annotated[Literal[10, 20, 50], BeforeValidator(_as_int)] | None = None


class YandexSearch(ScrapeRequest):
    """GET /api/yandex/search"""

    path: ClassVar[str] = "/api/yandex/search"
    endpoint: Literal["yandex_search"] = "yandex_search"
    yandex_domain: YandexDomain | None = None
    family_mode: Annotated[Literal[0, 1, 2], BeforeValidator(_as_int)] | None = None
    p: Annotated[int, Field(ge=0)] | None = None
    text: Annotated[str, Field(min_length=1, max_length=400)]
    lang: str | None = None
    lr: Annotated[int, Field(ge=0)] | None = None
    fix_typo: bool | None = None
    groups_on_page: Annotated[int, Field(ge=1)] | None = None
    sort_mode: Literal["relevance", "date"] | None = None
    period: Literal["all", "day", "last_two_weeks", "month"] | None = None


class YandexImages(ScrapeRequest):
    """GET /api/yandex/images"""

    path: ClassVar[str] = "/api/yandex/images"
    endpoint: Literal["yandex_images"] = "yandex_images"
    yandex_domain: YandexDomain | None = None
    family_mode: Annotated[Literal[0, 1, 2], BeforeValidator(_as_int)] | None = None
    p: Annotated[int, Field(ge=0)] | None = None
    text: Annotated[str, Field(min_length=1)] | None = None
    width: Annotated[int, Field(gt=0)] | None = None
    height: Annotated[int, Field(gt=0)] | None = None
    file_type: Literal["jpg", "png", "gifan"] | None = None
    color: (
        Literal[
            "color", "gray", "red", "orange", "yellow", "cyan", "green", "blue", "violet", "white", "black"
        ]
        | None
    ) = None
    orientation: Literal["horizontal", "vertical", "square"] | None = None
    image_type: Literal["photo", "clipart", "lineart", "demotivator", "face"] | None = None
    site: str | None = None
    recent: bool | None = None
    url: str | None = None
    crop: str | None = None
    crop_id: str | None = None
    tab: Literal["about", "similar"] | None = None

    @model_validator(mode="after")
    def _check_yandex_images(self) -> YandexImages:
        _require_any(self, "text", "url")
        _paired(self, "width", "height")
        _at_most_one(self, "crop", "crop_id")
        for name in ("crop", "crop_id", "tab"):
            _requires(self, name, "url")
        return self


class NaverSearch(ScrapeRequest):
    """GET /api/naver/search"""

    path: ClassVar[str] = "/api/naver/search"
    endpoint: Literal["naver_search"] = "naver_search"
    query: Annotated[str, Field(min_length=1, max_length=4096)]
    start: Annotated[int, Field(ge=0)] | None = None
    page: Annotated[int, Field(ge=1)] | None = None
    num: Annotated[int, Field(ge=1, le=100)] | None = None
    where: Literal["nexearch", "web", "video", "news", "image"] | None = None
    sort_by: Literal["r", "dd", "0", "1", "2"] | None = None
    period: str | None = None

    @model_validator(mode="after")
    def _check_naver(self) -> NaverSearch:
        if self.num is not None and self.where != "image":
            raise ValueError("num requires where=image")
        allowed = {"0", "1", "2"} if self.where == "news" else {"r", "dd"}
        if self.sort_by is not None and self.sort_by not in allowed:
            raise ValueError("sort_by must be 0, 1, or 2 for news, or r or dd for other searches")
        return self


class NaverAiOverview(ScrapeRequest):
    """GET /api/naver/ai-overview"""

    path: ClassVar[str] = "/api/naver/ai-overview"
    endpoint: Literal["naver_ai_overview"] = "naver_ai_overview"
    query: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    page_token: Annotated[str, Field(min_length=1, max_length=2048)] | None = None

    @model_validator(mode="after")
    def _check_naver_ai_overview(self) -> NaverAiOverview:
        _exactly_one(self, "query", "page_token")
        return self


class CopilotChatCompletions(ScrapeRequest):
    """Alpha. POST /api/copilot/chat/completions: a text answer from Microsoft Copilot, sent as a JSON body.

    Each call starts a fresh conversation; resend earlier ``messages`` for context. The last message must
    come from the user. ``state`` (a US postal code) requires ``country="US"``. Streaming is unsupported.
    """

    path: ClassVar[str] = "/api/copilot/chat/completions"
    endpoint: Literal["copilot_chat_completions"] = "copilot_chat_completions"
    method: ClassVar[str] = "POST"
    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=32)]
    model: Literal["copilot"] | None = None
    stream: Literal[False] | None = None
    country: CountryCode | None = None
    state: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None = None

    @model_validator(mode="after")
    def _check_copilot(self) -> CopilotChatCompletions:
        if self.messages[-1].role != "user":
            raise ValueError("the final message must have role user")
        if sum(len(message.content) for message in self.messages) > 32000:
            raise ValueError("total message content must not exceed 32,000 characters")
        if self.state is not None and self.country != "US":
            raise ValueError("state requires country=US")
        return self


class YahooSearch(ScrapeRequest):
    """GET /api/yahoo/search"""

    path: ClassVar[str] = "/api/yahoo/search"
    endpoint: Literal["yahoo_search"] = "yahoo_search"
    p: Annotated[str, Field(min_length=1, max_length=2000)]
    yahoo_domain: str | None = None
    b: Annotated[int, Field(ge=1, le=10001)] | None = None
    device: Device | None = None
    vc: Annotated[str, Field(pattern=r"^[a-z]{2}$")] | None = None
    vl: Annotated[str, Field(pattern=r"^lang_(?:[a-z]{2}|zh_chs|zh_cht)$")] | None = None
    vm: Literal["r", "i", "p"] | None = None
    vs: Annotated[str, Field(max_length=500)] | None = None
    vf: Annotated[str, Field(max_length=80)] | None = None
    fr2: Annotated[str, Field(max_length=1000)] | None = None
    d: Annotated[str, Field(max_length=4096)] | None = None


class YahooImages(ScrapeRequest):
    """GET /api/yahoo/images"""

    path: ClassVar[str] = "/api/yahoo/images"
    endpoint: Literal["yahoo_images"] = "yahoo_images"
    p: Annotated[str, Field(min_length=1, max_length=2000)]
    yahoo_domain: str | None = None
    b: Annotated[int, Field(ge=1, le=10001)] | None = None
    device: Device | None = None
    imgsz: Literal["small", "medium", "large", "wallpaper"] | None = None
    imgc: (
        Literal[
            "color",
            "bw",
            "red",
            "orange",
            "yellow",
            "green",
            "teal",
            "blue",
            "purple",
            "pink",
            "brown",
            "black",
            "gray",
            "white",
        ]
        | None
    ) = None
    imgty: Literal["photo", "clipart", "linedrawing", "gif", "transparent"] | None = None
    imga: Literal["square", "wide", "tall"] | None = None
    imgf: Literal["face", "portrait", "nonportrait"] | None = None
    imgt: Literal["day", "week", "month", "year"] | None = None
    imgl: Literal["cc", "pd", "fsu", "fsuc", "fmsu", "fmsuc"] | None = None


class AirbnbSearch(ScrapeRequest):
    """GET /api/airbnb/search"""

    path: ClassVar[str] = "/api/airbnb/search"
    endpoint: Literal["airbnb_search"] = "airbnb_search"
    q: Annotated[str, Field(max_length=500)] | None = None
    map_bounds: str | None = None
    airbnb_domain: str | None = None
    currency: str | None = None
    check_in_date: str | None = None
    check_out_date: str | None = None
    adults: Annotated[int, Field(ge=0)] | None = None
    children: Annotated[int, Field(ge=0)] | None = None
    infants: Annotated[int, Field(ge=0)] | None = None
    pets: Annotated[int, Field(ge=0)] | None = None
    room_type: Literal["entire_home", "private_room"] | None = None
    min_price: Annotated[float, Field(ge=0)] | None = None
    max_price: Annotated[float, Field(ge=0)] | None = None
    bedrooms: Annotated[int, Field(ge=0)] | None = None
    beds: Annotated[int, Field(ge=0)] | None = None
    bathrooms: Annotated[float, Field(ge=0)] | None = None
    property_types: str | None = None
    amenities: str | None = None
    accessibility_features: str | None = None
    host_languages: str | None = None
    instant_book: bool | None = None
    self_check_in: bool | None = None
    guest_favorite: bool | None = None
    luxe: bool | None = None
    page: Annotated[int, Field(ge=1, le=15)] | None = None

    @model_validator(mode="after")
    def _check_airbnb(self) -> AirbnbSearch:
        _require_any(self, "q", "map_bounds")
        _paired(self, "check_in_date", "check_out_date")
        _ordered(self, "min_price", "max_price")
        return self


class EventbriteSearch(ScrapeRequest):
    """GET /api/eventbrite/search"""

    path: ClassVar[str] = "/api/eventbrite/search"
    endpoint: Literal["eventbrite_search"] = "eventbrite_search"
    location: (
        Annotated[str, Field(max_length=150, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+|--[a-z0-9]+)*$")] | None
    ) = None
    q: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^\S+(?: \S+)*$")] | None = None
    page: Annotated[int, Field(ge=1, le=100)] | None = None


class IndeedSearch(ScrapeRequest):
    """GET /api/indeed/search"""

    path: ClassVar[str] = "/api/indeed/search"
    endpoint: Literal["indeed_search"] = "indeed_search"
    q: JobText | None = None
    page: Annotated[int, Field(ge=1)] | None = None
    page_token: JobPageToken | None = None
    location: JobText | None = None
    radius: Annotated[int, Field(ge=0, le=100)] | None = None
    radius_unit: Literal["miles", "kilometers"] | None = None
    country: CountryCode | None = None
    locale: Annotated[str, Field(pattern=r"^[a-z]{2,3}-[A-Z]{2}$")] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] | None = None
    sort: Literal["relevance", "date"] | None = None
    fromage: Annotated[int, Field(ge=1)] | None = None
    job_type: (
        Literal[
            "fulltime",
            "parttime",
            "contract",
            "temporary",
            "internship",
            "permanent",
            "temp_to_hire",
            "freelance",
        ]
        | None
    ) = None
    workplace: Literal["remote", "hybrid"] | None = None
    easy_apply: bool | None = None
    education: Literal["high_school", "associate", "bachelor", "master", "doctoral"] | None = None
    no_experience: bool | None = None
    experience_level: Literal["entry", "mid", "senior"] | None = None
    salary_min: Annotated[int, Field(ge=0)] | None = None
    salary_max: Annotated[int, Field(ge=0)] | None = None
    experience_months_min: Annotated[int, Field(ge=0)] | None = None
    experience_months_max: Annotated[int, Field(ge=0)] | None = None
    job_language: Annotated[str, Field(pattern=r"^[a-z]{2,3}$")] | None = None
    employer_keys: JobKeys | None = None
    attribute_keys: JobKeys | None = None
    any_attribute_keys: JobKeys | None = None

    @model_validator(mode="after")
    def _check_indeed(self) -> IndeedSearch:
        _requires_later_page(self)
        _ordered(self, "salary_min", "salary_max")
        _ordered(self, "experience_months_min", "experience_months_max")
        return self


class GlassdoorSearch(ScrapeRequest):
    """GET /api/glassdoor/search"""

    path: ClassVar[str] = "/api/glassdoor/search"
    endpoint: Literal["glassdoor_search"] = "glassdoor_search"
    q: JobText | None = None
    page: Annotated[int, Field(ge=1)] | None = None
    location: JobText | None = None
    page_token: JobPageToken | None = None
    location_id: Annotated[int, Field(ge=1)] | None = None
    location_type: Literal["C", "S", "N"] | None = None
    location_country: CountryCode | None = None
    radius: Annotated[int, Field(ge=0, le=100)] | None = None
    job_type: Literal["fulltime", "parttime", "contract", "temporary", "internship", "permanent"] | None = (
        None
    )
    job_types: JobKeys | None = None
    from_age: Annotated[int, Field(ge=1, le=30)] | None = None
    salary_min: Annotated[int, Field(ge=0)] | None = None
    salary_max: Annotated[int, Field(ge=0)] | None = None
    remote: bool | None = None
    easy_apply: bool | None = None
    seniority: Literal["internship", "entrylevel", "midseniorlevel", "director", "executive"] | None = None
    company_id: Annotated[int, Field(ge=1)] | None = None
    company_sizes: Annotated[list[int], Field(min_length=1, max_length=100)] | None = None
    industry_id: Annotated[int, Field(ge=1)] | None = None
    occupation_id: Annotated[int, Field(ge=1)] | None = None
    city_id: Annotated[int, Field(ge=1)] | None = None
    min_rating: Annotated[float, Field(ge=0, le=5)] | None = None
    sort: Literal["relevance", "date_asc", "date_desc"] | None = None
    include_filters: bool | None = None

    @model_validator(mode="after")
    def _check_glassdoor(self) -> GlassdoorSearch:
        _requires_later_page(self)
        _paired(self, "location_id", "location_type")
        _at_most_one(self, "location", "location_id")
        _requires(self, "location_country", "location")
        _at_most_one(self, "job_type", "job_types")
        if self.company_sizes and any(size not in range(1, 6) for size in self.company_sizes):
            raise ValueError("company_sizes must be categories 1 through 5")
        _ordered(self, "salary_min", "salary_max")
        return self


class AshbySearch(ScrapeRequest):
    """GET /api/ashby/search"""

    path: ClassVar[str] = "/api/ashby/search"
    endpoint: Literal["ashby_search"] = "ashby_search"
    q: JobText | None = None
    page: Annotated[int, Field(ge=1)] | None = None
    board: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")]
    location: JobText | None = None
    department: JobText | None = None
    team: JobText | None = None
    workplace_type: Literal["OnSite", "Remote", "Hybrid"] | None = None
    country: JobText | None = None
    region: JobText | None = None
    city: JobText | None = None
    remote: bool | None = None
    employment_type: Literal["FullTime", "PartTime", "Intern", "Contract", "Temporary"] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] | None = None
    include_compensation: bool | None = None


class ZipRecruiterSearch(ScrapeRequest):
    """GET /api/ziprecruiter/search"""

    path: ClassVar[str] = "/api/ziprecruiter/search"
    endpoint: Literal["ziprecruiter_search"] = "ziprecruiter_search"
    q: JobText
    page: Annotated[int, Field(ge=1)] | None = None
    location: JobText
    radius: Annotated[int, Field(ge=0, le=5000)] | None = None
    days: Annotated[int, Field(ge=1)] | None = None
    employment_types: (
        Annotated[
            list[
                Literal[
                    "full_time",
                    "part_time",
                    "contract",
                    "contract_to_hire",
                    "temporary",
                    "as_needed",
                    "other",
                ]
            ],
            Field(min_length=1, max_length=100),
        ]
        | None
    ) = None
    location_type: Literal["no_remote", "only_remote", "hybrid"] | None = None
    salary_min: Annotated[int, Field(ge=0)] | None = None
    salary_max: Annotated[int, Field(ge=0)] | None = None
    experience_level: Literal["no_experience", "junior", "mid", "senior"] | None = None
    easy_apply: bool | None = None

    @model_validator(mode="after")
    def _check_ziprecruiter(self) -> ZipRecruiterSearch:
        if self.salary_min is not None and self.salary_max is not None and self.salary_min >= self.salary_max:
            raise ValueError("salary_max must be greater than salary_min")
        return self


class LevelsSearch(ScrapeRequest):
    """GET /api/levels/search"""

    path: ClassVar[str] = "/api/levels/search"
    endpoint: Literal["levels_search"] = "levels_search"
    q: JobText | None = None
    page: Annotated[int, Field(ge=1)] | None = None
    company: LevelsSlug | None = None
    location: LevelsSlug | None = None
    sort: Literal["relevance", "date_published", "total_compensation"] | None = None
    limit: Annotated[int, Field(ge=1, le=20)] | None = None
    jobs_per_company: Annotated[int, Field(ge=1, le=15)] | None = None
    companies: Annotated[list[LevelsSlug], Field(min_length=1, max_length=100)] | None = None
    locations: Annotated[list[LevelsSlug], Field(min_length=1, max_length=100)] | None = None
    job_families: Annotated[list[LevelsSlug], Field(min_length=1, max_length=100)] | None = None
    levels: (
        Annotated[
            list[
                Literal["internship", "entry", "mid_staff", "principal", "manager", "director", "executive"]
            ],
            Field(min_length=1, max_length=100),
        ]
        | None
    ) = None
    employment_types: (
        Annotated[
            list[
                Literal["full_time", "part_time", "contract", "temporary", "internship", "volunteer", "other"]
            ],
            Field(min_length=1, max_length=100),
        ]
        | None
    ) = None
    work_arrangements: (
        Annotated[list[Literal["remote", "office", "hybrid"]], Field(min_length=1, max_length=100)] | None
    ) = None
    min_base_compensation: Annotated[int, Field(ge=0)] | None = None
    min_total_compensation: Annotated[int, Field(ge=0)] | None = None
    company_types: (
        Annotated[
            list[Literal["private", "public", "nonprofit", "government", "education", "delisted"]],
            Field(min_length=1, max_length=100),
        ]
        | None
    ) = None
    company_sizes: (
        Annotated[
            list[Literal["seed", "early", "mid", "large", "enterprise"]], Field(min_length=1, max_length=100)
        ]
        | None
    ) = None
    company_valuations: (
        Annotated[
            list[Annotated[tuple[int, int], Field(min_length=2, max_length=2)]],
            Field(min_length=1, max_length=100),
        ]
        | None
    ) = None
    perk_ids: Annotated[list[int], Field(min_length=1, max_length=100)] | None = None
    posted_within: Annotated[int, Field(ge=1)] | None = None
    posted_within_unit: Literal["days", "weeks", "months"] | None = None

    @model_validator(mode="after")
    def _check_levels(self) -> LevelsSearch:
        _at_most_one(self, "company", "companies")
        _at_most_one(self, "location", "locations")
        if self.company_valuations and any(low < 0 or high < low for low, high in self.company_valuations):
            raise ValueError("company_valuations ranges must be nonnegative [minimum, maximum] pairs")
        if self.perk_ids and any(perk < 1 for perk in self.perk_ids):
            raise ValueError("perk_ids must be positive")
        return self


class ZillowSearch(ScrapeRequest):
    """GET /api/zillow/search"""

    path: ClassVar[str] = "/api/zillow/search"
    endpoint: Literal["zillow_search"] = "zillow_search"
    min_price: Annotated[int, Field(ge=0)] | None = None
    max_price: Annotated[int, Field(ge=0)] | None = None
    min_beds: Annotated[int, Field(ge=0, le=20)] | None = None
    max_beds: Annotated[int, Field(ge=0, le=20)] | None = None
    min_baths: Annotated[float, Field(ge=0, le=20)] | None = None
    min_sqft: Annotated[int, Field(ge=0)] | None = None
    max_sqft: Annotated[int, Field(ge=0)] | None = None
    q: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    map_bounds: str | None = None
    status: Literal["for_sale", "for_rent", "sold"] | None = None
    property_type: (
        Literal["house", "condo", "townhouse", "multi_family", "land", "manufactured", "apartment"] | None
    ) = None
    sort: Literal["recommended", "newest", "price_asc", "price_desc", "beds", "sqft"] | None = None
    page: Annotated[int, Field(ge=1, le=20)] | None = None

    @model_validator(mode="after")
    def _check_zillow(self) -> ZillowSearch:
        _exactly_one(self, "q", "map_bounds")
        for name in ("price", "beds", "sqft"):
            _ordered(self, f"min_{name}", f"max_{name}")
        return self


class ZillowProperty(ScrapeRequest):
    """GET /api/zillow/property"""

    path: ClassVar[str] = "/api/zillow/property"
    endpoint: Literal["zillow_property"] = "zillow_property"
    zpid: Annotated[int, Field(gt=0)] | None = None
    url: Annotated[str, Field(max_length=2048)] | None = None

    @model_validator(mode="after")
    def _check_zillow_property(self) -> ZillowProperty:
        _exactly_one(self, "zpid", "url")
        return self


class ZillowLocations(ScrapeRequest):
    """GET /api/zillow/locations"""

    path: ClassVar[str] = "/api/zillow/locations"
    endpoint: Literal["zillow_locations"] = "zillow_locations"
    q: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    type: Literal["regions", "addresses"] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] | None = None
    page_token: Annotated[str, Field(min_length=1, max_length=32768)] | None = None

    @model_validator(mode="after")
    def _check_zillow_locations(self) -> ZillowLocations:
        if self.page_token is not None:
            _alone(self, "page_token")
        elif self.q is None:
            raise ValueError("q is required unless page_token is supplied")
        return self


class RedfinSearch(ScrapeRequest):
    """GET /api/redfin/search"""

    path: ClassVar[str] = "/api/redfin/search"
    endpoint: Literal["redfin_search"] = "redfin_search"
    min_price: Annotated[int, Field(ge=0)] | None = None
    max_price: Annotated[int, Field(ge=0)] | None = None
    min_beds: Annotated[int, Field(ge=0, le=20)] | None = None
    max_beds: Annotated[int, Field(ge=0, le=20)] | None = None
    min_baths: Annotated[float, Field(ge=0, le=20)] | None = None
    min_sqft: Annotated[int, Field(ge=0)] | None = None
    max_sqft: Annotated[int, Field(ge=0)] | None = None
    url: Annotated[str, Field(max_length=2048)] | None = None
    region_id: Annotated[int, Field(gt=0)] | None = None
    region_type: Annotated[Literal[1, 2, 5, 6, 11], BeforeValidator(_as_int)] | None = None
    map_bounds: str | None = None
    status: Literal["for_sale", "sold"] | None = None
    sold_within_days: Annotated[int, Field(ge=1, le=365)] | None = None
    property_type: (
        Literal["house", "condo", "townhouse", "multi_family", "land", "other", "manufactured", "co_op"]
        | None
    ) = None
    sort: Literal["recommended", "newest", "price_asc", "price_desc", "sqft"] | None = None
    limit: Annotated[int, Field(ge=1, le=350)] | None = None

    @model_validator(mode="after")
    def _check_redfin(self) -> RedfinSearch:
        _paired(self, "region_id", "region_type")
        _exactly_one(self, "url", "region_id", "map_bounds")
        if self.sold_within_days is not None and self.status != "sold":
            raise ValueError("sold_within_days requires status=sold")
        for name in ("price", "beds", "sqft"):
            _ordered(self, f"min_{name}", f"max_{name}")
        return self


class RedfinProperty(ScrapeRequest):
    """GET /api/redfin/property"""

    path: ClassVar[str] = "/api/redfin/property"
    endpoint: Literal["redfin_property"] = "redfin_property"
    url: Annotated[str, Field(max_length=2048)]


class RealtorSearch(ScrapeRequest):
    """Alpha. GET /api/realtor/search"""

    path: ClassVar[str] = "/api/realtor/search"
    endpoint: Literal["realtor_search"] = "realtor_search"
    limit: Annotated[int, Field(ge=1, le=200)] | None = None
    url: Annotated[str, Field(max_length=4096)]


class RealtorProperty(ScrapeRequest):
    """Alpha. GET /api/realtor/property"""

    path: ClassVar[str] = "/api/realtor/property"
    endpoint: Literal["realtor_property"] = "realtor_property"
    url: Annotated[str, Field(max_length=2048)]


class ApartmentsSearch(ScrapeRequest):
    """Alpha. GET /api/apartments/search"""

    path: ClassVar[str] = "/api/apartments/search"
    endpoint: Literal["apartments_search"] = "apartments_search"
    url: Annotated[str, Field(max_length=4096)]


class ApartmentsProperty(ScrapeRequest):
    """Alpha. GET /api/apartments/property"""

    path: ClassVar[str] = "/api/apartments/property"
    endpoint: Literal["apartments_property"] = "apartments_property"
    url: Annotated[str, Field(max_length=2048)]


class HomesSearch(ScrapeRequest):
    """Alpha. GET /api/homes/search"""

    path: ClassVar[str] = "/api/homes/search"
    endpoint: Literal["homes_search"] = "homes_search"
    url: Annotated[str, Field(max_length=4096)]


class HomesProperty(ScrapeRequest):
    """Alpha. GET /api/homes/property"""

    path: ClassVar[str] = "/api/homes/property"
    endpoint: Literal["homes_property"] = "homes_property"
    url: Annotated[str, Field(max_length=2048)]


class FacebookSearchPages(ScrapeRequest):
    """Alpha. GET /api/facebook/search-pages"""

    path: ClassVar[str] = "/api/facebook/search-pages"
    endpoint: Literal["facebook_search_pages"] = "facebook_search_pages"
    query: FacebookQuery
    limit: Annotated[int, Field(ge=1, le=15)] | None = None
    country: CountryCode | None = None
    ad_type: Literal["ALL", "POLITICAL_AND_ISSUE_ADS"] | None = None


class FacebookSearchProfiles(ScrapeRequest):
    """Alpha. GET /api/facebook/search-profiles"""

    path: ClassVar[str] = "/api/facebook/search-profiles"
    endpoint: Literal["facebook_search_profiles"] = "facebook_search_profiles"
    query: FacebookQuery
    limit: Annotated[int, Field(ge=1, le=12)] | None = None


class FacebookHashtagPosts(ScrapeRequest):
    """Alpha. GET /api/facebook/hashtag-posts"""

    path: ClassVar[str] = "/api/facebook/hashtag-posts"
    endpoint: Literal["facebook_hashtag_posts"] = "facebook_hashtag_posts"
    tag: Annotated[str, Field(pattern=r"^#?[A-Za-z0-9_]{1,100}$")]
    limit: Annotated[int, Field(ge=1, le=20)] | None = None
    continuation_token: Annotated[str, Field(min_length=1, max_length=32768)] | None = None


class FacebookPost(ScrapeRequest):
    """Alpha. GET /api/facebook/post"""

    path: ClassVar[str] = "/api/facebook/post"
    endpoint: Literal["facebook_post"] = "facebook_post"
    url: Annotated[
        str,
        Field(
            max_length=400,
            pattern=r"^https://www\.facebook\.com/[A-Za-z0-9][A-Za-z0-9._-]*/posts/(?:[0-9]+|pfbid[A-Za-z0-9]+)/?$",
        ),
    ]


class FacebookPagePosts(ScrapeRequest):
    """Alpha. GET /api/facebook/page-posts"""

    path: ClassVar[str] = "/api/facebook/page-posts"
    endpoint: Literal["facebook_page_posts"] = "facebook_page_posts"
    handle: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")]


class FacebookMarketplaceBrowse(ScrapeRequest):
    """Alpha. GET /api/facebook/marketplace-browse"""

    path: ClassVar[str] = "/api/facebook/marketplace-browse"
    endpoint: Literal["facebook_marketplace_browse"] = "facebook_marketplace_browse"
    limit: Annotated[int, Field(ge=1, le=26)] | None = None
    location: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")] | None = None
    query: FacebookQuery | None = None
    radius_km: Annotated[int, Field(ge=1, le=500)] | None = None
    min_price: Annotated[float, Field(ge=0, le=10000000)] | None = None
    max_price: Annotated[float, Field(ge=0, le=10000000)] | None = None
    sort_by: Literal["price_ascend", "price_descend", "creation_time_descend"] | None = None
    condition: Literal["new", "used_like_new", "used_good", "used_fair"] | None = None
    days_since_listed: Annotated[int, Field(ge=1, le=30)] | None = None
    continuation_token: (
        Annotated[str, Field(min_length=1, max_length=32768, pattern=r"^m1\.[A-Za-z0-9_-]+$")] | None
    ) = None

    @model_validator(mode="after")
    def _check_marketplace(self) -> FacebookMarketplaceBrowse:
        _requires(self, "query", "location")
        _requires(self, "radius_km", "location")
        for name in (
            "min_price",
            "max_price",
            "sort_by",
            "condition",
            "days_since_listed",
            "continuation_token",
        ):
            _requires(self, name, "query")
        _ordered(self, "min_price", "max_price")
        return self


class FacebookReel(ScrapeRequest):
    """Alpha. GET /api/facebook/reel"""

    path: ClassVar[str] = "/api/facebook/reel"
    endpoint: Literal["facebook_reel"] = "facebook_reel"
    url: Annotated[str, Field(max_length=150, pattern=r"^https://www\.facebook\.com/reel/[0-9]{1,30}/?$")]


class YouTubeSearch(ScrapeRequest):
    """GET /api/youtube/search"""

    path: ClassVar[str] = "/api/youtube/search"
    endpoint: Literal["youtube_search"] = "youtube_search"
    type: Literal["video", "shorts", "channel", "playlist", "movie"] | None = None
    upload_date: Literal["today", "this_week", "this_month", "this_year"] | None = None
    duration: Literal["under_3_min", "between_3_and_20_min", "over_20_min"] | None = None
    features: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    sort_by: Literal["relevance", "popularity"] | None = None
    q: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    hl: Annotated[str, Field(pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,2}$")] | None = None
    gl: Annotated[str, Field(pattern=r"^[A-Za-z]{2}$")] | None = None
    sp: Annotated[str, Field(min_length=1, max_length=2048, pattern=r"^[a-zA-Z0-9_+/=%-]+$")] | None = None
    page_token: (
        Annotated[str, Field(min_length=1, max_length=32768, pattern=r"^ct2_[A-Za-z0-9_-]{100,}$")] | None
    ) = None

    @model_validator(mode="after")
    def _check_youtube_search(self) -> YouTubeSearch:
        if self.page_token is not None:
            _alone(self, "page_token")
            return self
        if self.q is None:
            raise ValueError("q is required unless page_token is supplied")
        if self.sp is not None:
            _at_most_one(self, "sp", "type", "upload_date", "duration", "features", "sort_by")
        if self.type in ("channel", "playlist"):
            for name in ("upload_date", "duration", "features"):
                if getattr(self, name) is not None:
                    raise ValueError(f"{name} is not available for type={self.type}")
        if self.type == "shorts" and self.duration is not None:
            raise ValueError("duration is not available for type=shorts")
        return self


class YouTubeChannel(ScrapeRequest):
    """GET /api/youtube/channel"""

    path: ClassVar[str] = "/api/youtube/channel"
    endpoint: Literal["youtube_channel"] = "youtube_channel"
    channel_id: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    tab: Literal["videos", "shorts", "streams", "podcasts", "playlists", "posts"] | None = None
    sort: Literal["latest", "popular", "oldest", "dd", "lad"] | None = None
    search_query: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    hl: Annotated[str, Field(pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,2}$")] | None = None
    gl: Annotated[str, Field(pattern=r"^[A-Za-z]{2}$")] | None = None
    about: bool | None = None
    next_page_token: (
        Annotated[str, Field(min_length=1, max_length=32768, pattern=r"^ct2_[A-Za-z0-9_-]{100,}$")] | None
    ) = None

    @model_validator(mode="after")
    def _check_youtube_channel(self) -> YouTubeChannel:
        if self.next_page_token is not None:
            _alone(self, "next_page_token")
            return self
        if self.channel_id is None:
            raise ValueError("channel_id is required unless next_page_token is supplied")
        _at_most_one(self, "search_query", "tab")
        _at_most_one(self, "search_query", "sort")
        return self


class AmazonSearch(ScrapeRequest):
    """Alpha. GET /api/amazon/search"""

    path: ClassVar[str] = "/api/amazon/search"
    endpoint: Literal["amazon_search"] = "amazon_search"
    amazon_domain: str | None = None
    language: Annotated[str, Field(pattern=r"^[a-z]{2}_[A-Z]{2}$")] | None = None
    delivery_zip: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    shipping_location: CountryCode | None = None
    k: Annotated[str, Field(min_length=1)] | None = None
    node: Annotated[str, Field(pattern=r"^[0-9]+$")] | None = None
    s: (
        Literal[
            "relevanceblender",
            "price-asc-rank",
            "price-desc-rank",
            "review-rank",
            "date-desc-rank",
            "exact-aware-popularity-rank",
        ]
        | None
    ) = None
    rh: str | None = None
    dc: bool | None = None
    page: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def _check_amazon_search(self) -> AmazonSearch:
        _exactly_one(self, "k", "node")
        return self


class AmazonProduct(ScrapeRequest):
    """Alpha. GET /api/amazon/product"""

    path: ClassVar[str] = "/api/amazon/product"
    endpoint: Literal["amazon_product"] = "amazon_product"
    amazon_domain: str | None = None
    language: Annotated[str, Field(pattern=r"^[a-z]{2}_[A-Z]{2}$")] | None = None
    delivery_zip: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    shipping_location: CountryCode | None = None
    asin: Asin
    other_sellers: bool | None = None
    all_related_products: bool | None = None


class AmazonAutocomplete(ScrapeRequest):
    """Alpha. GET /api/amazon/autocomplete"""

    path: ClassVar[str] = "/api/amazon/autocomplete"
    endpoint: Literal["amazon_autocomplete"] = "amazon_autocomplete"
    amazon_domain: str | None = None
    k: Annotated[str, Field(min_length=1)]
    amazon_department: Annotated[str, Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")] | None = None


class AmazonFeaturedReviews(ScrapeRequest):
    """Alpha. GET /api/amazon/featured-reviews"""

    path: ClassVar[str] = "/api/amazon/featured-reviews"
    endpoint: Literal["amazon_featured_reviews"] = "amazon_featured_reviews"
    asin: Asin
    amazon_domain: AmazonDomain | None = None


class AmazonMediaReviews(ScrapeRequest):
    """Alpha. GET /api/amazon/media-reviews"""

    path: ClassVar[str] = "/api/amazon/media-reviews"
    endpoint: Literal["amazon_media_reviews"] = "amazon_media_reviews"
    asin: Asin | None = None
    amazon_domain: AmazonDomain | None = None
    view: Literal["media", "images", "videos"] | None = None
    page_token: (
        Annotated[str, Field(min_length=5, max_length=8196, pattern=r"^ar1\.[A-Za-z0-9_-]+$")] | None
    ) = None

    @model_validator(mode="after")
    def _check_amazon_media_reviews(self) -> AmazonMediaReviews:
        if self.page_token is not None:
            _alone(self, "page_token")
        elif self.asin is None:
            raise ValueError("asin is required unless page_token is supplied")
        return self


class XProfile(ScrapeRequest):
    """Alpha. GET /api/x/profile"""

    path: ClassVar[str] = "/api/x/profile"
    endpoint: Literal["x_profile"] = "x_profile"
    username: XUsername


class XPost(ScrapeRequest):
    """Alpha. GET /api/x/post"""

    path: ClassVar[str] = "/api/x/post"
    endpoint: Literal["x_post"] = "x_post"
    post_id: XId


class XUserPosts(ScrapeRequest):
    """Alpha. GET /api/x/user-posts"""

    path: ClassVar[str] = "/api/x/user-posts"
    endpoint: Literal["x_user_posts"] = "x_user_posts"
    username: XUsername
    cursor: Annotated[str, Field(min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9_+/=-]+$")] | None = None


class XCommunity(ScrapeRequest):
    """Alpha. GET /api/x/community"""

    path: ClassVar[str] = "/api/x/community"
    endpoint: Literal["x_community"] = "x_community"
    community_id: XId


class XCommunityPosts(ScrapeRequest):
    """Alpha. GET /api/x/community-posts"""

    path: ClassVar[str] = "/api/x/community-posts"
    endpoint: Literal["x_community_posts"] = "x_community_posts"
    community_id: XId


class EbaySearch(ScrapeRequest):
    """GET /api/ebay/search

    eBay's underscore parameters are fields without the underscore (``nkw`` is sent as ``_nkw``,
    ``pgn`` as ``_pgn``, ...); dicts may use either spelling.
    """

    path: ClassVar[str] = "/api/ebay/search"
    endpoint: Literal["ebay_search"] = "ebay_search"
    ebay_domain: EbayDomain | None = None
    nkw: Annotated[str, Field(min_length=1, max_length=500)] | None = Field(None, alias="_nkw")
    category_id: Annotated[int, Field(ge=1)] | None = None
    pgn: Annotated[int, Field(ge=1)] | None = Field(None, alias="_pgn")
    ipg: Annotated[Literal[25, 50, 100, 200], BeforeValidator(_as_int)] | None = Field(None, alias="_ipg")
    sop: Annotated[Literal[1, 2, 3, 7, 10, 12, 15, 16, 18, 19], BeforeValidator(_as_int)] | None = Field(
        None, alias="_sop"
    )
    udlo: Annotated[float, Field(ge=0)] | None = Field(None, alias="_udlo")
    udhi: Annotated[float, Field(ge=0)] | None = Field(None, alias="_udhi")
    buying_format: Literal["Auction", "BIN", "BO"] | None = None
    LH_ItemCondition: Annotated[str, Field(pattern=r"^[0-9]{1,4}(\|[0-9]{1,4}){0,9}$")] | None = None
    stpos: Annotated[str, Field(min_length=1, max_length=20)] | None = Field(None, alias="_stpos")
    salic: int | None = Field(None, alias="_salic")
    blrs: Literal["spell_auto_correct"] | None = Field(None, alias="_blrs")
    show_only: Annotated[str, Field(max_length=100)] | None = None
    sasl: Annotated[str, Field(max_length=1000)] | None = Field(None, alias="_sasl")
    saslop: Annotated[Literal[1, 2], BeforeValidator(_as_int)] | None = Field(None, alias="_saslop")
    popular_filters: Annotated[str, Field(max_length=4000)] | None = None
    dmd: Literal["Grid", "List"] | None = Field(None, alias="_dmd")
    LH_PrefLoc: Literal["Domestic", "Regional", "Worldwide"] | None = None

    @model_validator(mode="after")
    def _check_ebay_search(self) -> EbaySearch:
        if self.nkw is None and self.category_id is None:
            raise ValueError("one of _nkw, category_id is required")
        _ordered(self, "udlo", "udhi")
        return self


class EbayProduct(ScrapeRequest):
    """GET /api/ebay/product"""

    path: ClassVar[str] = "/api/ebay/product"
    endpoint: Literal["ebay_product"] = "ebay_product"
    ebay_domain: EbayDomain | None = None
    product_id: Annotated[str, Field(pattern=r"^[0-9]{12}$")]
    locale: str | None = None
    lang: Annotated[str, Field(max_length=12, pattern=r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")] | None = None
    shipping_country: str | None = None

    @model_validator(mode="after")
    def _check_ebay_product(self) -> EbayProduct:
        if self.lang is not None and (self.locale is None or self.ebay_domain not in (None, "ebay.com")):
            raise ValueError("lang requires locale and ebay_domain=ebay.com")
        return self


class EbaySeller(ScrapeRequest):
    """GET /api/ebay/seller (``pgn``, ``ipg`` and ``sop`` are sent as ``_pgn``, ``_ipg`` and ``_sop``)"""

    path: ClassVar[str] = "/api/ebay/seller"
    endpoint: Literal["ebay_seller"] = "ebay_seller"
    ebay_domain: EbayDomain | None = None
    seller_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.*-]{0,99}$")]
    type: Literal["user", "store"]
    pgn: Annotated[int, Field(ge=1)] | None = Field(None, alias="_pgn")
    ipg: Annotated[Literal[24, 48, 72], BeforeValidator(_as_int)] | None = Field(None, alias="_ipg")
    sop: Annotated[Literal[1, 7, 10, 12, 15, 16], BeforeValidator(_as_int)] | None = Field(None, alias="_sop")
    buying_format: Annotated[Literal[0, 1, 2], BeforeValidator(_as_int)] | None = None
    LH_ItemCondition: (
        Annotated[str, Field(max_length=20, pattern=r"^(?:3|4|10)(?:\|(?:3|4|10))*$")] | None
    ) = None
    free_shipping: bool | None = None


class TikTokProfile(ScrapeRequest):
    """Alpha. GET /api/tiktok/profile"""

    path: ClassVar[str] = "/api/tiktok/profile"
    endpoint: Literal["tiktok_profile"] = "tiktok_profile"
    handle: TikTokHandle | None = None
    user_id: NumericId | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokProfile:
        _exactly_one(self, "handle", "user_id")
        return self


class TikTokVideo(ScrapeRequest):
    """Alpha. GET /api/tiktok/video"""

    path: ClassVar[str] = "/api/tiktok/video"
    endpoint: Literal["tiktok_video"] = "tiktok_video"
    url: Annotated[str, Field(max_length=2048)] | None = None
    video_id: NumericId | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokVideo:
        _exactly_one(self, "url", "video_id")
        return self


class TikTokTranscript(ScrapeRequest):
    """Alpha. GET /api/tiktok/transcript"""

    path: ClassVar[str] = "/api/tiktok/transcript"
    endpoint: Literal["tiktok_transcript"] = "tiktok_transcript"
    url: Annotated[str, Field(max_length=2048)] | None = None
    video_id: NumericId | None = None
    language: Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")] | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokTranscript:
        _exactly_one(self, "url", "video_id")
        return self


class TikTokSearchSuggestions(ScrapeRequest):
    """Alpha. GET /api/tiktok/search-suggestions"""

    path: ClassVar[str] = "/api/tiktok/search-suggestions"
    endpoint: Literal["tiktok_search_suggestions"] = "tiktok_search_suggestions"
    query: Annotated[str, Field(min_length=1, max_length=500)]


class TikTokUserLive(ScrapeRequest):
    """Alpha. GET /api/tiktok/user-live"""

    path: ClassVar[str] = "/api/tiktok/user-live"
    endpoint: Literal["tiktok_user_live"] = "tiktok_user_live"
    handle: TikTokHandle


class TikTokLive(ScrapeRequest):
    """Alpha. GET /api/tiktok/live"""

    path: ClassVar[str] = "/api/tiktok/live"
    endpoint: Literal["tiktok_live"] = "tiktok_live"
    room_id: NumericId


class TikTokSong(ScrapeRequest):
    """Alpha. GET /api/tiktok/song"""

    path: ClassVar[str] = "/api/tiktok/song"
    endpoint: Literal["tiktok_song"] = "tiktok_song"
    clip_id: NumericId


class TikTokProfileVideos(ScrapeRequest):
    """Alpha. GET /api/tiktok/profile-videos"""

    path: ClassVar[str] = "/api/tiktok/profile-videos"
    endpoint: Literal["tiktok_profile_videos"] = "tiktok_profile_videos"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    handle: TikTokHandle | None = None
    user_id: NumericId | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokProfileVideos:
        _exactly_one(self, "handle", "user_id")
        return self


class TikTokComments(ScrapeRequest):
    """Alpha. GET /api/tiktok/comments"""

    path: ClassVar[str] = "/api/tiktok/comments"
    endpoint: Literal["tiktok_comments"] = "tiktok_comments"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    url: Annotated[str, Field(max_length=2048)] | None = None
    video_id: NumericId | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokComments:
        _exactly_one(self, "url", "video_id")
        return self


class TikTokCommentReplies(ScrapeRequest):
    """Alpha. GET /api/tiktok/comment-replies"""

    path: ClassVar[str] = "/api/tiktok/comment-replies"
    endpoint: Literal["tiktok_comment_replies"] = "tiktok_comment_replies"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    url: Annotated[str, Field(max_length=2048)] | None = None
    video_id: NumericId | None = None
    comment_id: NumericId

    @model_validator(mode="after")
    def _check_target(self) -> TikTokCommentReplies:
        _exactly_one(self, "url", "video_id")
        return self


class TikTokFollowing(ScrapeRequest):
    """Alpha. GET /api/tiktok/following"""

    path: ClassVar[str] = "/api/tiktok/following"
    endpoint: Literal["tiktok_following"] = "tiktok_following"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    handle: TikTokHandle | None = None
    user_id: NumericId | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokFollowing:
        _exactly_one(self, "handle", "user_id")
        return self


class TikTokFollowers(ScrapeRequest):
    """Alpha. GET /api/tiktok/followers"""

    path: ClassVar[str] = "/api/tiktok/followers"
    endpoint: Literal["tiktok_followers"] = "tiktok_followers"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    handle: TikTokHandle | None = None
    user_id: NumericId | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokFollowers:
        _exactly_one(self, "handle", "user_id")
        return self


class TikTokSearchKeyword(ScrapeRequest):
    """Alpha. GET /api/tiktok/search-keyword"""

    path: ClassVar[str] = "/api/tiktok/search-keyword"
    endpoint: Literal["tiktok_search_keyword"] = "tiktok_search_keyword"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    query: Annotated[str, Field(min_length=1, max_length=500)]
    search_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")] | None = None


class TikTokSearchTop(ScrapeRequest):
    """Alpha. GET /api/tiktok/search-top"""

    path: ClassVar[str] = "/api/tiktok/search-top"
    endpoint: Literal["tiktok_search_top"] = "tiktok_search_top"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    query: Annotated[str, Field(min_length=1, max_length=500)]
    search_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")] | None = None


class TikTokSearchHashtag(ScrapeRequest):
    """Alpha. GET /api/tiktok/search-hashtag"""

    path: ClassVar[str] = "/api/tiktok/search-hashtag"
    endpoint: Literal["tiktok_search_hashtag"] = "tiktok_search_hashtag"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    hashtag: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^#?[^\s#/&?=]+$")]


class TikTokSongVideos(ScrapeRequest):
    """Alpha. GET /api/tiktok/song-videos"""

    path: ClassVar[str] = "/api/tiktok/song-videos"
    endpoint: Literal["tiktok_song_videos"] = "tiktok_song_videos"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    clip_id: NumericId


class TikTokTrendingFeed(ScrapeRequest):
    """Alpha. GET /api/tiktok/trending-feed"""

    path: ClassVar[str] = "/api/tiktok/trending-feed"
    endpoint: Literal["tiktok_trending_feed"] = "tiktok_trending_feed"
    count: TikTokCount | None = None


class TikTokCollectionVideos(ScrapeRequest):
    """Alpha. GET /api/tiktok/collection-videos"""

    path: ClassVar[str] = "/api/tiktok/collection-videos"
    endpoint: Literal["tiktok_collection_videos"] = "tiktok_collection_videos"
    cursor: NumericId | None = None
    count: TikTokCount | None = None
    url: Annotated[str, Field(max_length=2048)] | None = None
    collection_id: NumericId | None = None

    @model_validator(mode="after")
    def _check_target(self) -> TikTokCollectionVideos:
        _exactly_one(self, "url", "collection_id")
        return self


class InstagramProfile(ScrapeRequest):
    """Alpha. GET /api/instagram/profile"""

    path: ClassVar[str] = "/api/instagram/profile"
    endpoint: Literal["instagram_profile"] = "instagram_profile"
    handle: InstagramHandle
    trim: bool | None = None


class InstagramPosts(ScrapeRequest):
    """Alpha. GET /api/instagram/posts"""

    path: ClassVar[str] = "/api/instagram/posts"
    endpoint: Literal["instagram_posts"] = "instagram_posts"
    handle: InstagramHandle
    trim: bool | None = None
    next_max_id: Annotated[str, Field(min_length=1, max_length=8192)] | None = None
    num: Annotated[int, Field(ge=1, le=50)] | None = None


class InstagramPost(ScrapeRequest):
    """Alpha. GET /api/instagram/post"""

    path: ClassVar[str] = "/api/instagram/post"
    endpoint: Literal["instagram_post"] = "instagram_post"
    url: str
    trim: bool | None = None


class InstagramProfilePostCount(ScrapeRequest):
    """Alpha. GET /api/instagram/profile-post-count"""

    path: ClassVar[str] = "/api/instagram/profile-post-count"
    endpoint: Literal["instagram_profile_post_count"] = "instagram_profile_post_count"
    handle: InstagramHandle


class InstagramEmbed(ScrapeRequest):
    """Alpha. GET /api/instagram/embed"""

    path: ClassVar[str] = "/api/instagram/embed"
    endpoint: Literal["instagram_embed"] = "instagram_embed"
    handle: InstagramHandle


class InstagramSearchPopular(ScrapeRequest):
    """Alpha. GET /api/instagram/search-popular"""

    path: ClassVar[str] = "/api/instagram/search-popular"
    endpoint: Literal["instagram_search_popular"] = "instagram_search_popular"
    query: Annotated[str, Field(min_length=1, max_length=200)]
    cursor: Annotated[str, Field(min_length=1, max_length=8192)] | None = None


class WalmartSearch(ScrapeRequest):
    """Alpha. GET /api/walmart/search"""

    path: ClassVar[str] = "/api/walmart/search"
    endpoint: Literal["walmart_search"] = "walmart_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None


class WalmartProduct(ScrapeRequest):
    """Alpha. GET /api/walmart/product"""

    path: ClassVar[str] = "/api/walmart/product"
    endpoint: Literal["walmart_product"] = "walmart_product"
    url: ProductUrl


class HomeDepotSearch(ScrapeRequest):
    """Alpha. GET /api/homedepot/search"""

    path: ClassVar[str] = "/api/homedepot/search"
    endpoint: Literal["homedepot_search"] = "homedepot_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=1)] | None = None


class HomeDepotProduct(ScrapeRequest):
    """Alpha. GET /api/homedepot/product"""

    path: ClassVar[str] = "/api/homedepot/product"
    endpoint: Literal["homedepot_product"] = "homedepot_product"
    url: ProductUrl


class TargetSearch(ScrapeRequest):
    """Alpha. GET /api/target/search"""

    path: ClassVar[str] = "/api/target/search"
    endpoint: Literal["target_search"] = "target_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None
    store_id: StoreId | None = None


class TargetProduct(ScrapeRequest):
    """Alpha. GET /api/target/product"""

    path: ClassVar[str] = "/api/target/product"
    endpoint: Literal["target_product"] = "target_product"
    url: ProductUrl
    store_id: StoreId | None = None


class EtsySearch(ScrapeRequest):
    """Alpha. GET /api/etsy/search"""

    path: ClassVar[str] = "/api/etsy/search"
    endpoint: Literal["etsy_search"] = "etsy_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None


class EtsyProduct(ScrapeRequest):
    """Alpha. GET /api/etsy/product"""

    path: ClassVar[str] = "/api/etsy/product"
    endpoint: Literal["etsy_product"] = "etsy_product"
    url: ProductUrl


class BestBuySearch(ScrapeRequest):
    """Alpha. GET /api/bestbuy/search"""

    path: ClassVar[str] = "/api/bestbuy/search"
    endpoint: Literal["bestbuy_search"] = "bestbuy_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None
    store_id: StoreId | None = None


class BestBuyProduct(ScrapeRequest):
    """Alpha. GET /api/bestbuy/product"""

    path: ClassVar[str] = "/api/bestbuy/product"
    endpoint: Literal["bestbuy_product"] = "bestbuy_product"
    url: ProductUrl
    store_id: StoreId | None = None


class WayfairSearch(ScrapeRequest):
    """Alpha. GET /api/wayfair/search"""

    path: ClassVar[str] = "/api/wayfair/search"
    endpoint: Literal["wayfair_search"] = "wayfair_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None


class WayfairProduct(ScrapeRequest):
    """Alpha. GET /api/wayfair/product"""

    path: ClassVar[str] = "/api/wayfair/product"
    endpoint: Literal["wayfair_product"] = "wayfair_product"
    url: ProductUrl


class AliExpressSearch(ScrapeRequest):
    """Alpha. GET /api/aliexpress/search"""

    path: ClassVar[str] = "/api/aliexpress/search"
    endpoint: Literal["aliexpress_search"] = "aliexpress_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None


class AliExpressProduct(ScrapeRequest):
    """Alpha. GET /api/aliexpress/product"""

    path: ClassVar[str] = "/api/aliexpress/product"
    endpoint: Literal["aliexpress_product"] = "aliexpress_product"
    url: ProductUrl


class KrogerSearch(ScrapeRequest):
    """Alpha. GET /api/kroger/search"""

    path: ClassVar[str] = "/api/kroger/search"
    endpoint: Literal["kroger_search"] = "kroger_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=1)] | None = None
    store_id: StoreId | None = None


class KrogerProduct(ScrapeRequest):
    """Alpha. GET /api/kroger/product"""

    path: ClassVar[str] = "/api/kroger/product"
    endpoint: Literal["kroger_product"] = "kroger_product"
    url: ProductUrl
    store_id: StoreId | None = None


class SproutsSearch(ScrapeRequest):
    """Alpha. GET /api/sprouts/search"""

    path: ClassVar[str] = "/api/sprouts/search"
    endpoint: Literal["sprouts_search"] = "sprouts_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None
    store_id: StoreId | None = None


class SproutsProduct(ScrapeRequest):
    """Alpha. GET /api/sprouts/product"""

    path: ClassVar[str] = "/api/sprouts/product"
    endpoint: Literal["sprouts_product"] = "sprouts_product"
    url: ProductUrl
    store_id: StoreId | None = None


class WholeFoodsSearch(ScrapeRequest):
    """Alpha. GET /api/wholefoods/search"""

    path: ClassVar[str] = "/api/wholefoods/search"
    endpoint: Literal["wholefoods_search"] = "wholefoods_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None
    store_id: StoreId | None = None


class WholeFoodsProduct(ScrapeRequest):
    """Alpha. GET /api/wholefoods/product"""

    path: ClassVar[str] = "/api/wholefoods/product"
    endpoint: Literal["wholefoods_product"] = "wholefoods_product"
    url: ProductUrl
    store_id: StoreId | None = None


class IkeaSearch(ScrapeRequest):
    """Alpha. GET /api/ikea/search"""

    path: ClassVar[str] = "/api/ikea/search"
    endpoint: Literal["ikea_search"] = "ikea_search"
    query: RetailQuery
    page: Annotated[int, Field(ge=1, le=100)] | None = None
    store_id: StoreId | None = None


class IkeaProduct(ScrapeRequest):
    """Alpha. GET /api/ikea/product"""

    path: ClassVar[str] = "/api/ikea/product"
    endpoint: Literal["ikea_product"] = "ikea_product"
    url: ProductUrl
    store_id: StoreId | None = None


_REQUEST_CLASSES: tuple[type[ScrapeRequest], ...] = (
    GoogleSearch,
    GoogleAiOverview,
    GoogleAiMode,
    GoogleGemini,
    GoogleAds,
    GoogleShopping,
    GoogleShoppingProduct,
    GoogleShoppingMerchantUrls,
    GoogleLocal,
    GoogleImages,
    GoogleJobs,
    GoogleMaps,
    GoogleMapsLiveFootTraffic,
    GoogleMapsPosts,
    GoogleMapsPhoto,
    GoogleReviews,
    GoogleContributorReviews,
    BingSearch,
    BingMaps,
    BingImages,
    BingShopping,
    BingProduct,
    DuckDuckGoSearch,
    DuckDuckGoMaps,
    YelpSearch,
    YelpReviews,
    YelpPlace,
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
    WebScreenshot,
    BraveSearch,
    BraveAiMode,
    BaiduSearch,
    YandexSearch,
    YandexImages,
    NaverSearch,
    NaverAiOverview,
    CopilotChatCompletions,
    YahooSearch,
    YahooImages,
    AirbnbSearch,
    EventbriteSearch,
    IndeedSearch,
    GlassdoorSearch,
    AshbySearch,
    ZipRecruiterSearch,
    LevelsSearch,
    ZillowSearch,
    ZillowProperty,
    ZillowLocations,
    RedfinSearch,
    RedfinProperty,
    RealtorSearch,
    RealtorProperty,
    ApartmentsSearch,
    ApartmentsProperty,
    HomesSearch,
    HomesProperty,
    FacebookSearchPages,
    FacebookSearchProfiles,
    FacebookHashtagPosts,
    FacebookPost,
    FacebookPagePosts,
    FacebookMarketplaceBrowse,
    FacebookReel,
    YouTubeSearch,
    YouTubeChannel,
    AmazonSearch,
    AmazonProduct,
    AmazonAutocomplete,
    AmazonFeaturedReviews,
    AmazonMediaReviews,
    XProfile,
    XPost,
    XUserPosts,
    XCommunity,
    XCommunityPosts,
    EbaySearch,
    EbayProduct,
    EbaySeller,
    TikTokProfile,
    TikTokVideo,
    TikTokTranscript,
    TikTokSearchSuggestions,
    TikTokUserLive,
    TikTokLive,
    TikTokSong,
    TikTokProfileVideos,
    TikTokComments,
    TikTokCommentReplies,
    TikTokFollowing,
    TikTokFollowers,
    TikTokSearchKeyword,
    TikTokSearchTop,
    TikTokSearchHashtag,
    TikTokSongVideos,
    TikTokTrendingFeed,
    TikTokCollectionVideos,
    InstagramProfile,
    InstagramPosts,
    InstagramPost,
    InstagramProfilePostCount,
    InstagramEmbed,
    InstagramSearchPopular,
    WalmartSearch,
    WalmartProduct,
    HomeDepotSearch,
    HomeDepotProduct,
    TargetSearch,
    TargetProduct,
    EtsySearch,
    EtsyProduct,
    BestBuySearch,
    BestBuyProduct,
    WayfairSearch,
    WayfairProduct,
    AliExpressSearch,
    AliExpressProduct,
    KrogerSearch,
    KrogerProduct,
    SproutsSearch,
    SproutsProduct,
    WholeFoodsSearch,
    WholeFoodsProduct,
    IkeaSearch,
    IkeaProduct,
)

AnyRequest = Annotated[
    GoogleSearch
    | GoogleAiOverview
    | GoogleAiMode
    | GoogleGemini
    | GoogleAds
    | GoogleShopping
    | GoogleShoppingProduct
    | GoogleShoppingMerchantUrls
    | GoogleLocal
    | GoogleImages
    | GoogleJobs
    | GoogleMaps
    | GoogleMapsLiveFootTraffic
    | GoogleMapsPosts
    | GoogleMapsPhoto
    | GoogleReviews
    | GoogleContributorReviews
    | BingSearch
    | BingMaps
    | BingImages
    | BingShopping
    | BingProduct
    | DuckDuckGoSearch
    | DuckDuckGoMaps
    | YelpSearch
    | YelpReviews
    | YelpPlace
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
    | WebFetch
    | WebScreenshot
    | BraveSearch
    | BraveAiMode
    | BaiduSearch
    | YandexSearch
    | YandexImages
    | NaverSearch
    | NaverAiOverview
    | CopilotChatCompletions
    | YahooSearch
    | YahooImages
    | AirbnbSearch
    | EventbriteSearch
    | IndeedSearch
    | GlassdoorSearch
    | AshbySearch
    | ZipRecruiterSearch
    | LevelsSearch
    | ZillowSearch
    | ZillowProperty
    | ZillowLocations
    | RedfinSearch
    | RedfinProperty
    | RealtorSearch
    | RealtorProperty
    | ApartmentsSearch
    | ApartmentsProperty
    | HomesSearch
    | HomesProperty
    | FacebookSearchPages
    | FacebookSearchProfiles
    | FacebookHashtagPosts
    | FacebookPost
    | FacebookPagePosts
    | FacebookMarketplaceBrowse
    | FacebookReel
    | YouTubeSearch
    | YouTubeChannel
    | AmazonSearch
    | AmazonProduct
    | AmazonAutocomplete
    | AmazonFeaturedReviews
    | AmazonMediaReviews
    | XProfile
    | XPost
    | XUserPosts
    | XCommunity
    | XCommunityPosts
    | EbaySearch
    | EbayProduct
    | EbaySeller
    | TikTokProfile
    | TikTokVideo
    | TikTokTranscript
    | TikTokSearchSuggestions
    | TikTokUserLive
    | TikTokLive
    | TikTokSong
    | TikTokProfileVideos
    | TikTokComments
    | TikTokCommentReplies
    | TikTokFollowing
    | TikTokFollowers
    | TikTokSearchKeyword
    | TikTokSearchTop
    | TikTokSearchHashtag
    | TikTokSongVideos
    | TikTokTrendingFeed
    | TikTokCollectionVideos
    | InstagramProfile
    | InstagramPosts
    | InstagramPost
    | InstagramProfilePostCount
    | InstagramEmbed
    | InstagramSearchPopular
    | WalmartSearch
    | WalmartProduct
    | HomeDepotSearch
    | HomeDepotProduct
    | TargetSearch
    | TargetProduct
    | EtsySearch
    | EtsyProduct
    | BestBuySearch
    | BestBuyProduct
    | WayfairSearch
    | WayfairProduct
    | AliExpressSearch
    | AliExpressProduct
    | KrogerSearch
    | KrogerProduct
    | SproutsSearch
    | SproutsProduct
    | WholeFoodsSearch
    | WholeFoodsProduct
    | IkeaSearch
    | IkeaProduct,
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
