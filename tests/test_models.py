from __future__ import annotations

import json
import pathlib
import typing

import pydantic
import pytest

from litescrape_sdk import (
    REQUEST_TYPES,
    AnyRequest,
    AppleMapsPlaces,
    BingMaps,
    BingSearch,
    DuckDuckGoMaps,
    DuckDuckGoSearch,
    GoogleAds,
    GoogleAiMode,
    GoogleMaps,
    GoogleReviews,
    GoogleSearch,
    GoogleShopping,
    GoogleShoppingProduct,
    TripadvisorPlace,
    TripadvisorSearch,
    YelpSearch,
)
from litescrape_sdk.models import _REQUEST_CLASSES, REQUEST_ADAPTER

ALLOWLISTS = json.loads((pathlib.Path(__file__).parent / "allowlists.json").read_text())

PATHS = {
    "google_play_apps": "/api/google/play/apps",
    "google_play_games": "/api/google/play/games",
    "google_play_books": "/api/google/play/books",
    "google_play_movies": "/api/google/play/movies",
    "google_play_product": "/api/google/play/product",
    "google_play_reviews": "/api/google/play/reviews",
    "apple_app_store_search": "/api/apple/app-store/search",
    "apple_app_store_product": "/api/apple/app-store/product",
    "apple_app_store_reviews": "/api/apple/app-store/reviews",
    "google_search": "/api/google/search",
    "google_ai_overview": "/api/google/ai-overview",
    "google_ai_mode": "/api/google/ai-mode",
    "google_ads": "/api/google/ads",
    "google_shopping": "/api/google/shopping",
    "google_shopping_product": "/api/google/shopping/product",
    "google_local": "/api/google/local",
    "google_maps": "/api/google/maps",
    "google_maps_live_foot_traffic": "/api/google/maps/popular-times",
    "google_maps_posts": "/api/google/maps/posts",
    "google_maps_photo": "/api/google/maps/photo-meta",
    "google_maps_web_results": "/api/google/maps/web",
    "google_reviews": "/api/google/reviews",
    "google_contributor_reviews": "/api/google/contributor-reviews",
    "bing_search": "/api/bing/search",
    "bing_maps": "/api/bing/maps",
    "duckduckgo_search": "/api/duckduckgo/search",
    "duckduckgo_maps": "/api/duckduckgo/maps",
    "yelp_search": "/api/yelp/search",
    "yelp_reviews": "/api/yelp/reviews",
    "tripadvisor_search": "/api/tripadvisor/search",
    "tripadvisor_place": "/api/tripadvisor/place",
    "tripadvisor_reviews": "/api/tripadvisor/reviews",
    "apple_maps_places": "/api/apple/maps/places",
    "apple_maps_reviews": "/api/apple/maps/reviews",
}


def test_registry_covers_every_endpoint():
    assert set(REQUEST_TYPES) == set(ALLOWLISTS) == set(PATHS)
    assert len(REQUEST_TYPES) == 34
    assert {slug: cls.path for slug, cls in REQUEST_TYPES.items()} == PATHS


def test_union_members_match_registry():
    union = typing.get_args(AnyRequest)[0]
    assert set(typing.get_args(union)) == set(_REQUEST_CLASSES) == set(REQUEST_TYPES.values())


@pytest.mark.parametrize("slug", sorted(ALLOWLISTS))
def test_model_fields_match_allowlist(slug):
    assert set(REQUEST_TYPES[slug].model_fields) - {"endpoint"} == set(ALLOWLISTS[slug])


def test_dict_and_typed_inputs_are_equivalent():
    from_dict = REQUEST_ADAPTER.validate_python(
        {"endpoint": "google_search", "q": "x", "num": "10", "nfpr": 1}
    )
    typed = GoogleSearch(q="x", num=10, nfpr=True)
    assert from_dict == typed
    assert from_dict.query_params() == typed.query_params() == {"q": "x", "num": "10", "nfpr": "1"}


@pytest.mark.parametrize(
    "value, normalized", [(True, "true"), (False, "false"), ("true", "true"), ("false", "false")]
)
def test_search_fast_mode(value, normalized):
    assert GoogleSearch(q="coffee", fast_mode=value).query_params()["fast_mode"] == normalized
    assert "fast_mode" not in GoogleSearch(q="coffee").query_params()
    with pytest.raises(pydantic.ValidationError):
        REQUEST_TYPES["google_ai_overview"](q="coffee", fast_mode=value)


@pytest.mark.parametrize("value", [0, 1, "", "TRUE", "yes", "1", " true"])
def test_search_fast_mode_rejects_ambiguous_values(value):
    with pytest.raises(pydantic.ValidationError):
        GoogleSearch(q="coffee", fast_mode=value)


def test_typed_instances_pass_through_unchanged():
    request = GoogleSearch(q="x")
    assert REQUEST_ADAPTER.validate_python(request) is request


def test_query_serialization():
    request = GoogleMaps(q="coffee", type="search", nearby=True, lat=40.5, lon=-73.9, z=14, start=0, hl="")
    assert request.query_params() == {
        "q": "coffee",
        "type": "search",
        "nearby": "true",
        "lat": "40.5",
        "lon": "-73.9",
        "z": "14.0",
        "start": "0",
        "hl": "",
    }
    assert GoogleShopping(q="x", on_sale=False).query_params() == {"q": "x", "on_sale": "false"}


def test_numbers_coerce_to_strings_for_string_fields():
    assert AppleMapsPlaces(muid=4372355869446211302).query_params()["muid"] == "4372355869446211302"
    assert TripadvisorPlace(place_id=123).query_params()["place_id"] == "123"


def test_flag_and_enum_coercion():
    assert GoogleSearch(q="x", nfpr=False, filter=0).query_params() == {"q": "x", "nfpr": "0", "filter": "0"}
    assert GoogleShopping(q="x", sort_by=2).query_params()["sort_by"] == "2"
    assert DuckDuckGoSearch(q="x", safe=-1).query_params()["safe"] == "-1"
    assert BingSearch(q="x", engine="bing").query_params() == {"engine": "bing", "q": "x"}


@pytest.mark.parametrize(
    "item, fragment",
    [
        ({"q": "x"}, "endpoint"),
        ({"endpoint": "google", "q": "x"}, "google_search"),
        ({"endpoint": "google_search", "q": "x", "bogus": 1}, "bogus"),
        ({"endpoint": "google_search", "q": "x", "device": "Desktop"}, "device"),
        ({"endpoint": "google_search", "q": "x", "safe": "on"}, "safe"),
        ({"endpoint": "google_search", "q": "x", "nfpr": "2"}, "nfpr"),
        ({"endpoint": "google_search", "q": "x", "num": "ten"}, "num"),
        ("not a request", ""),
    ],
)
def test_invalid_items_are_rejected(item, fragment):
    with pytest.raises(pydantic.ValidationError) as info:
        REQUEST_ADAPTER.validate_python(item)
    assert fragment in str(info.value)


@pytest.mark.parametrize(
    "cls, kwargs, ok",
    [
        (GoogleSearch, {}, False),
        (GoogleSearch, {"kgmid": "/m/0k8z"}, True),
        (GoogleSearch, {"q": "x", "lat": 1.0}, False),
        (GoogleSearch, {"q": "x", "lat": 1.0, "lon": 2.0}, True),
        (GoogleSearch, {"q": "x", "location": "a", "uule": "b"}, False),
        (GoogleSearch, {"q": "x", "location": "a", "lat": 1.0, "lon": 2.0}, False),
        (GoogleSearch, {"q": "x", "as_nlo": "1"}, False),
        (GoogleSearch, {"q": "x", "as_nlo": "1", "as_nhi": "9"}, True),
        (GoogleSearch, {"q": "x", "as_dt": "i"}, False),
        (GoogleSearch, {"q": "x", "as_dt": "i", "as_sitesearch": "example.com"}, True),
        (GoogleAds, {"q": "x"}, False),
        (GoogleAds, {"q": "x", "location": "Austin, TX"}, True),
        (GoogleAiMode, {"q": "x", "image_url": "https://a/b.png", "subsequent_request_token": "t"}, False),
        (GoogleAiMode, {"q": "x", "location": "a", "uule": "b"}, False),
        (GoogleShopping, {}, False),
        (GoogleShopping, {"shoprs": "abc"}, True),
        (GoogleShopping, {"q": "x", "on_sale": True, "free_shipping": True}, False),
        (GoogleShopping, {"q": "x", "min_price": 1, "on_sale": True}, False),
        (GoogleShopping, {"q": "x", "on_sale": True, "free_shipping": False}, True),
        (GoogleShoppingProduct, {"q": "x"}, False),
        (GoogleShoppingProduct, {"q": "x", "gpcid": "1", "prds": "p"}, False),
        (GoogleShoppingProduct, {"q": "x", "prds": "p", "image_docid": "1"}, False),
        (GoogleShoppingProduct, {"q": "x", "gpcid": "1", "image_docid": "1"}, True),
        (GoogleMaps, {}, False),
        (GoogleMaps, {"q": "coffee"}, False),
        (GoogleMaps, {"q": "coffee", "type": "search"}, True),
        (GoogleMaps, {"type": "search"}, False),
        (GoogleMaps, {"place_id": "p"}, True),
        (GoogleMaps, {"place_id": "p", "data_cid": "1"}, False),
        (GoogleMaps, {"q": "c", "type": "search", "ll": "@1,2,14z", "lat": 1.0, "lon": 2.0}, False),
        (GoogleMaps, {"q": "c", "type": "search", "lat": 1.0, "lon": 2.0, "z": 14}, True),
        (GoogleMaps, {"q": "c", "type": "search", "z": 14, "m": 100}, False),
        (GoogleMaps, {"q": "c", "type": "search", "open_at_hour": 5}, False),
        (GoogleMaps, {"q": "c", "type": "search", "open_on_day": "mon", "open_at_hour": 5}, True),
        (GoogleMaps, {"q": "c", "type": "search", "open_state": "now", "open_on_day": "mon"}, False),
        (GoogleReviews, {}, False),
        (GoogleReviews, {"place_id": "a", "data_id": "b"}, False),
        (GoogleReviews, {"data_id": "0x1:0x2"}, True),
        (GoogleReviews, {"place_id": "a", "topic_id": "t", "query": "q"}, False),
        (BingSearch, {"q": "x", "mkt": "en-US", "cc": "US"}, False),
        (BingSearch, {"q": "x", "lat": 1.0}, True),
        (BingMaps, {}, False),
        (BingMaps, {"place_id": "x"}, True),
        (DuckDuckGoSearch, {"q": "x", "m": 10, "search_assist": False}, False),
        (DuckDuckGoMaps, {"q": "x"}, False),
        (DuckDuckGoMaps, {"q": "x", "bbox": "1,2,3,4"}, True),
        (DuckDuckGoMaps, {"q": "x", "lat": 1.0}, False),
        (DuckDuckGoMaps, {"q": "x", "lat": 1.0, "lon": 2.0}, True),
        (DuckDuckGoMaps, {"q": "x", "bbox": "1,2,3,4", "lat": 1.0, "lon": 2.0}, False),
        (TripadvisorSearch, {"q": "x", "lat": 1.0}, False),
        (YelpSearch, {"find_desc": "x"}, False),
        (AppleMapsPlaces, {}, False),
    ],
)
def test_presence_rules(cls, kwargs, ok):
    if ok:
        cls(**kwargs)
    else:
        with pytest.raises(pydantic.ValidationError):
            cls(**kwargs)
