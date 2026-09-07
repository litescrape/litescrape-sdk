"""Typed public request contracts for Apple App Store operations."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, field_validator

from ._store_countries import STOREFRONTS

Country = Annotated[str, StringConstraints(to_lower=True, pattern=r"^[a-zA-Z]{2}$")]
ProductId = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,19}$")]
Language = Annotated[str, StringConstraints(to_lower=True, pattern=r"^[a-zA-Z]{2,3}-[a-zA-Z]{2}$")]
SearchTerm = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]


class StoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=False)
    country: Country = "us"

    @field_validator("country")
    @classmethod
    def supported_country(cls, value: str) -> str:
        value = "gb" if value == "uk" else value
        if value not in STOREFRONTS:
            raise ValueError("Choose a supported Apple storefront country")
        return value

    @field_validator(
        "category_id",
        "country",
        "device",
        "disallow_explicit",
        "lang",
        "num",
        "page",
        "product_id",
        "property",
        "sort",
        "term",
        "type",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def reject_controls(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, str) and any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Control characters are not allowed")
        if info.field_name in {"num", "category_id", "page"} and value is not None:
            if type(value) is not int and not (
                isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip())
            ):
                raise ValueError("Use a whole number")
        if (
            info.field_name == "disallow_explicit"
            and type(value) is not bool
            and value not in ("true", "false")
        ):
            raise ValueError("Use true or false")
        return value


class AppleSearchRequest(StoreRequest):
    term: SearchTerm
    lang: Language = "en-us"
    num: Annotated[int, Field(ge=1, le=200)] = 10
    disallow_explicit: bool = False
    property: Literal["developer"] | None = None
    category_id: Annotated[int, Field(ge=1, le=2**31 - 1)] | None = None
    device: Literal["mobile", "tablet", "desktop"] = "mobile"


class AppleProductRequest(StoreRequest):
    product_id: ProductId
    type: Literal["app"] = "app"


class AppleReviewsRequest(StoreRequest):
    product_id: ProductId
    sort: Literal["mostrecent", "mosthelpful"] = "mostrecent"
    page: Annotated[int, Field(ge=1, le=2**31 - 1)] = 1


MODELS = {"search": AppleSearchRequest, "product": AppleProductRequest, "reviews": AppleReviewsRequest}
PARAMETERS = {operation: frozenset(model.model_fields) for operation, model in MODELS.items()}
PATHS = {operation: f"/api/apple/app-store/{operation}" for operation in MODELS}
APPLE_STORE_HOSTS = frozenset({"itunes.apple.com", "apps.apple.com"})
