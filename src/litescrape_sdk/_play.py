"""Typed request contracts for the Google Play storefront."""

from __future__ import annotations

import base64
import json
import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

Language = Annotated[
    str, StringConstraints(pattern=r"^[a-zA-Z]{2,3}(?:[-_][a-zA-Z0-9]{2,8}){0,3}$", max_length=32)
]
Country = Annotated[str, StringConstraints(to_lower=True, pattern=r"^[a-zA-Z]{2}$")]
Query = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    Field(description="At most 2,048 UTF-8 bytes.", json_schema_extra={"x-max-utf8-bytes": 2048}),
]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_.-]+$", min_length=1, max_length=512)]
Category = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]+$", min_length=1, max_length=128)]
Token = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_=+/:.-]+$", min_length=1, max_length=65536)]
Store = Literal["apps", "books", "audiobooks", "movies", "tv"]
Age = Literal["AGE_RANGE1", "AGE_RANGE2", "AGE_RANGE3"]
TOKEN_FIELDS = ("next_page_token", "section_page_token", "see_more_token")


class PlayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=False)
    hl: Language = "en"
    gl: Country = "us"

    @field_validator(
        "age",
        "apps_category",
        "books_category",
        "chart",
        "games_category",
        "gl",
        "hl",
        "movies_category",
        "next_page_token",
        "num",
        "platform",
        "price",
        "product_id",
        "q",
        "rating",
        "season_id",
        "section_page_token",
        "see_more_token",
        "sort_by",
        "store",
        "store_device",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def reject_controls(cls, value: Any, info: ValidationInfo) -> Any:
        if info.field_name == "q" and isinstance(value, str):
            try:
                size = len(value.strip().encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise ValueError("Use valid Unicode text") from exc
            if size > 2048:
                raise ValueError("Use at most 2,048 UTF-8 bytes")
        if isinstance(value, str) and any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Control characters are not allowed")
        if info.field_name in {"price", "rating", "sort_by", "num"} and value is not None:
            if type(value) is not int and not (
                isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip())
            ):
                raise ValueError("Use a whole number")
        return value

    @model_validator(mode="after")
    def cursor_context(self) -> PlayRequest:
        operation = getattr(self, "endpoint", "").removeprefix("google_play_")
        clean = self.model_dump(exclude_none=True, exclude={"endpoint"})
        if operation in {"apps", "games"} and not (clean.get("q") or clean.get(f"{operation}_category")):
            clean.setdefault("store_device", "phone")
        context = {key: value for key, value in clean.items() if key not in (*TOKEN_FIELDS, "chart")}
        for field in TOKEN_FIELDS:
            token = clean.get(field)
            if not token:
                continue
            kind = (
                ("reviews" if operation == "reviews" else "page")
                if field == "next_page_token"
                else ("section" if field == "section_page_token" else "collection")
            )
            try:
                value = json.loads(
                    base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
                )
                if (
                    not isinstance(value, dict)
                    or value.get("v") != 1
                    or value.get("operation") != operation
                    or value.get("context") != context
                    or value.get("kind") != kind
                    or not isinstance(value.get("token"), str)
                    or not re.fullmatch(r"[a-zA-Z0-9_=+/:.-]{1,12000}", value["token"])
                ):
                    raise ValueError("Changed token context")
            except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                raise ValueError(
                    "Use a returned token with the same operation and search parameters"
                ) from exc
        return self


class PlayListingRequest(PlayRequest):
    q: Query | None = None
    chart: Category | None = None
    next_page_token: Token | None = None
    section_page_token: Token | None = None
    see_more_token: Token | None = None

    @model_validator(mode="after")
    def listing_dependencies(self) -> PlayListingRequest:
        selectors = [key for key in (*TOKEN_FIELDS, "chart") if getattr(self, key)]
        if len(selectors) > 1:
            raise ValueError("chart and pagination selectors are mutually exclusive")
        if self.chart and self.q:
            raise ValueError("chart and q are mutually exclusive")
        if self.chart and getattr(self, "store_device", None) not in {None, "phone"}:
            raise ValueError("Device-specific storefronts do not support charts; omit chart or use phone")
        category = next(
            (getattr(self, key) for key in self.__class__.model_fields if key.endswith("_category")), None
        )
        if self.q and category:
            raise ValueError("q and category are mutually exclusive")
        if hasattr(self, "store_device") and self.store_device is not None and (self.q or category):
            raise ValueError("store_device excludes q and category")
        age = getattr(self, "age", None)
        if age and category != ("coll_1689" if isinstance(self, PlayBooksRequest) else "FAMILY"):
            raise ValueError("age requires the children's category")
        if getattr(self, "price", None) is not None and not self.q:
            raise ValueError("price requires q")
        return self


class PlayAppsRequest(PlayListingRequest):
    apps_category: Category | None = None
    store_device: Literal["phone", "tablet", "tv", "chromebook", "watch", "car"] | None = Field(
        default=None, json_schema_extra={"default": "phone"}
    )
    age: Age | None = None


class PlayGamesRequest(PlayListingRequest):
    games_category: Category | None = None
    store_device: Literal["phone", "tablet", "tv", "chromebook", "watch", "windows"] | None = Field(
        default=None, json_schema_extra={"default": "phone"}
    )


class PlayBooksRequest(PlayListingRequest):
    books_category: Category | None = None
    age: Age | None = None
    price: Annotated[int, Field(ge=1, le=2)] | None = None


class PlayMoviesRequest(PlayListingRequest):
    movies_category: Category | None = None
    age: Age | None = None


class PlayProductRequest(PlayRequest):
    product_id: Identifier
    store: Store = "apps"
    season_id: Identifier | None = None

    @model_validator(mode="after")
    def season_requires_tv(self) -> PlayProductRequest:
        if self.season_id and self.store != "tv":
            raise ValueError("season_id requires store=tv")
        return self


class PlayReviewsRequest(PlayRequest):
    product_id: Identifier
    store: Store = "apps"
    platform: Literal["phone", "tablet", "watch", "chromebook", "tv"] = "phone"
    rating: Annotated[int, Field(ge=1, le=5)] | None = None
    sort_by: Annotated[int, Field(ge=1, le=3)] = 1
    num: Annotated[int, Field(ge=1, le=199)] = 40
    next_page_token: Token | None = None


MODELS = {
    "apps": PlayAppsRequest,
    "games": PlayGamesRequest,
    "books": PlayBooksRequest,
    "movies": PlayMoviesRequest,
    "product": PlayProductRequest,
    "reviews": PlayReviewsRequest,
}
PARAMETERS = {operation: frozenset(model.model_fields) for operation, model in MODELS.items()}
PATHS = {operation: f"/api/google/play/{operation}" for operation in MODELS}
PLAY_HOSTS = frozenset({"play.google.com"})
DOCUMENT_TYPES = {"apps": 7, "books": 9, "audiobooks": 17, "movies": 1, "tv": 2}
FORM_FACTORS = {"phone": 2, "tablet": 3, "watch": 4, "chromebook": 5, "tv": 6, "car": 7}
