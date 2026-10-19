"""Every v3 endpoint: the API's own request examples, cross-field rules, and wire formats."""

from __future__ import annotations

import json
import pathlib

import pydantic
import pytest

from litescrape_sdk import (
    REQUEST_TYPES,
    AirbnbSearch,
    AmazonMediaReviews,
    AmazonSearch,
    BaiduSearch,
    BingImages,
    CopilotChatCompletions,
    EbayProduct,
    EbaySearch,
    FacebookMarketplaceBrowse,
    GlassdoorSearch,
    GoogleJobs,
    GoogleSearch,
    GoogleShoppingMerchantUrls,
    IndeedSearch,
    LevelsSearch,
    NaverAiOverview,
    NaverSearch,
    RedfinSearch,
    TikTokCollectionVideos,
    TikTokComments,
    TikTokProfile,
    WebScreenshot,
    YandexImages,
    YelpPlace,
    YelpReviews,
    YouTubeChannel,
    YouTubeSearch,
    ZillowLocations,
    ZillowProperty,
    ZillowSearch,
    ZipRecruiterSearch,
    ascrape,
    scrape,
)
from litescrape_sdk.models import REQUEST_ADAPTER

# Request examples published with the v3 API contract, keyed by route.
EXAMPLES = json.loads((pathlib.Path(__file__).parent / "endpoint_examples.json").read_text(encoding="utf-8"))
BY_PATH = {cls.path: slug for slug, cls in REQUEST_TYPES.items()}
POST_ENDPOINTS = {
    "web_fetch",
    "web_screenshot",
    "google_shopping_merchant_urls",
    "copilot_chat_completions",
}


def test_every_api_route_has_a_request_class():
    assert set(EXAMPLES) == set(BY_PATH)


@pytest.mark.parametrize("path", sorted(EXAMPLES))
def test_api_examples_validate(path):
    slug = BY_PATH[path]
    request = REQUEST_ADAPTER.validate_python({"endpoint": slug, **EXAMPLES[path]})
    assert request.path == path
    if request.method == "POST":
        assert request.body() == EXAMPLES[path]
    else:
        query = request.query_params()
        assert set(EXAMPLES[path]) <= set(query)
        # Query strings validate to the same request, so dicts built from URLs work too.
        assert REQUEST_ADAPTER.validate_python({"endpoint": slug, **query}).query_params() == query


def test_only_structured_endpoints_post_json():
    assert {slug for slug, cls in REQUEST_TYPES.items() if cls.method == "POST"} == POST_ENDPOINTS


def test_aliased_and_integer_choice_parameters():
    request = EbaySearch(nkw="lego", ipg="25", sop=12, LH_ItemCondition="1000|3000")
    assert request.query_params() == {
        "_nkw": "lego",
        "_ipg": "25",
        "_sop": "12",
        "LH_ItemCondition": "1000|3000",
    }
    assert REQUEST_ADAPTER.validate_python({"endpoint": "ebay_search", "_nkw": "lego"}) == EbaySearch(
        nkw="lego"
    )
    assert BaiduSearch(q="x", rn="20").query_params() == {"q": "x", "rn": "20"}
    with pytest.raises(pydantic.ValidationError):
        EbaySearch(nkw="lego", ipg=30)
    with pytest.raises(pydantic.ValidationError):
        BaiduSearch(q="x", rn="twenty")


def test_job_search_arrays_are_json_encoded_in_the_query():
    request = LevelsSearch(q="engineer", companies=["stripe", "openai"], company_valuations=[(0, 10)])
    assert request.query_params() == {
        "q": "engineer",
        "companies": '["stripe","openai"]',
        "company_valuations": "[[0,10]]",
    }
    indeed = IndeedSearch(q="x", employer_keys=["a1"], easy_apply=True)
    assert indeed.query_params() == {"q": "x", "employer_keys": '["a1"]', "easy_apply": "true"}


def test_numeric_ids_accept_integers():
    request = TikTokComments(video_id=7681307586901134622, cursor=20, count=5)
    assert request.query_params() == {"cursor": "20", "count": "5", "video_id": "7681307586901134622"}


def test_post_bodies_keep_native_types():
    chat = CopilotChatCompletions(
        messages=[{"role": "user", "content": "Weather?"}], country="US", state="CA", timeout=30
    )
    assert chat.body() == {
        "timeout": 30.0,
        "messages": [{"role": "user", "content": "Weather?"}],
        "country": "US",
        "state": "CA",
    }
    merchants = GoogleShoppingMerchantUrls(products=[{"headline_offer_docid": 514, "merchant": "Target"}])
    assert merchants.body() == {"products": [{"headline_offer_docid": "514", "merchant": "Target"}]}
    assert WebScreenshot(url="https://example.com", full_page=True).body() == {
        "url": "https://example.com",
        "full_page": True,
    }


def test_google_search_page_token_is_sent_alone():
    assert GoogleSearch(page_token="abc", timeout=10).query_params() == {
        "page_token": "abc",
        "timeout": "10.0",
    }
    with pytest.raises(pydantic.ValidationError, match="page_token"):
        GoogleSearch(page_token="abc", q="coffee")
    with pytest.raises(pydantic.ValidationError):
        REQUEST_TYPES["google_ai_overview"](page_token="abc")


@pytest.mark.parametrize(
    "cls, kwargs, ok",
    [
        (GoogleJobs, {"q": "x", "page_token": "abc"}, False),
        (GoogleJobs, {"q": "x", "page_token": "abc", "page": 2}, True),
        (GoogleJobs, {"q": "x", "radius": 5}, False),
        (GoogleJobs, {"q": "x", "lat": 1.0, "lon": 2.0, "radius": 5}, True),
        (GoogleJobs, {"q": "x", "location": "Austin", "uule": "w+CAIQ"}, False),
        (BingImages, {"q": "x", "mkt": "en-US", "cc": "US"}, False),
        (YandexImages, {}, False),
        (YandexImages, {"text": "x", "width": 10}, False),
        (YandexImages, {"text": "x", "tab": "similar"}, False),
        (YandexImages, {"url": "https://example.com/a.png", "tab": "similar"}, True),
        (NaverSearch, {"query": "x", "num": 10}, False),
        (NaverSearch, {"query": "x", "where": "image", "num": 10}, True),
        (NaverSearch, {"query": "x", "where": "news", "sort_by": "dd"}, False),
        (NaverAiOverview, {}, False),
        (NaverAiOverview, {"query": "x", "page_token": "t"}, False),
        (CopilotChatCompletions, {"messages": []}, False),
        (CopilotChatCompletions, {"messages": [{"role": "assistant", "content": "hi"}]}, False),
        (CopilotChatCompletions, {"messages": [{"role": "user", "content": " "}]}, False),
        (CopilotChatCompletions, {"messages": [{"role": "user", "content": "hi"}], "state": "CA"}, False),
        (CopilotChatCompletions, {"messages": [{"role": "user", "content": "hi"}], "stream": True}, False),
        (GoogleShoppingMerchantUrls, {"products": [{"headline_offer_docid": "1"}]}, False),
        (AirbnbSearch, {}, False),
        (AirbnbSearch, {"q": "Lisbon", "check_in_date": "2026-11-01"}, False),
        (AirbnbSearch, {"q": "Lisbon", "min_price": 200, "max_price": 100}, False),
        (IndeedSearch, {"q": "x", "salary_min": 9, "salary_max": 1}, False),
        (GlassdoorSearch, {"q": "x", "location_id": 1}, False),
        (GlassdoorSearch, {"q": "x", "location_id": 1, "location_type": "C"}, True),
        (GlassdoorSearch, {"q": "x", "location_country": "US"}, False),
        (GlassdoorSearch, {"q": "x", "company_sizes": [6]}, False),
        (ZipRecruiterSearch, {"q": "x", "location": "y", "salary_min": 5, "salary_max": 5}, False),
        (LevelsSearch, {"company": "stripe", "companies": ["openai"]}, False),
        (LevelsSearch, {"company_valuations": [(10, 1)]}, False),
        (ZillowSearch, {}, False),
        (ZillowSearch, {"q": "Austin, TX", "min_beds": 4, "max_beds": 2}, False),
        (ZillowProperty, {}, False),
        (ZillowProperty, {"zpid": 1, "url": "https://www.zillow.com/x"}, False),
        (ZillowLocations, {}, False),
        (ZillowLocations, {"page_token": "t", "q": "x"}, False),
        (ZillowLocations, {"page_token": "t"}, True),
        (RedfinSearch, {}, False),
        (RedfinSearch, {"region_id": 1}, False),
        (RedfinSearch, {"region_id": 1, "region_type": "6"}, True),
        (RedfinSearch, {"url": "https://www.redfin.com/x", "sold_within_days": 30}, False),
        (FacebookMarketplaceBrowse, {"query": "bike"}, False),
        (FacebookMarketplaceBrowse, {"location": "nyc", "min_price": 5}, False),
        (FacebookMarketplaceBrowse, {"location": "nyc", "query": "bike", "min_price": 5}, True),
        (YelpPlace, {"place_id": "x", "menu_name": "Dinner"}, False),
        (YelpReviews, {"place_id": "x", "not_recommended_start": 10}, False),
        (
            YelpReviews,
            {"place_id": "x", "q": "parking", "not_recommended": True, "not_recommended_start": 10},
            True,
        ),
        (YouTubeSearch, {}, False),
        (YouTubeSearch, {"q": "x", "sp": "EgIQAQ", "type": "video"}, False),
        (YouTubeSearch, {"q": "x", "type": "channel", "duration": "over_20_min"}, False),
        (YouTubeSearch, {"q": "x", "type": "shorts", "duration": "over_20_min"}, False),
        (YouTubeChannel, {}, False),
        (YouTubeChannel, {"channel_id": "@x", "search_query": "y", "tab": "videos"}, False),
        (AmazonSearch, {}, False),
        (AmazonSearch, {"k": "x", "node": "1"}, False),
        (AmazonMediaReviews, {}, False),
        (AmazonMediaReviews, {"page_token": "ar1.abc", "asin": "B000000000"}, False),
        (EbaySearch, {}, False),
        (EbaySearch, {"category_id": 1, "udlo": 9, "udhi": 1}, False),
        (EbayProduct, {"product_id": "123456789012", "lang": "en"}, False),
        (EbayProduct, {"product_id": "123456789012", "lang": "en", "locale": "en-US"}, True),
        (TikTokProfile, {}, False),
        (TikTokProfile, {"handle": "@x", "user_id": "1"}, False),
        (TikTokComments, {"video_id": "1", "url": "https://www.tiktok.com/@x/video/1"}, False),
        (TikTokComments, {"video_id": "1", "count": 36}, False),
        (TikTokCollectionVideos, {}, False),
    ],
)
def test_presence_rules(cls, kwargs, ok):
    if ok:
        cls(**kwargs)
    else:
        with pytest.raises(pydantic.ValidationError):
            cls(**kwargs)


def test_post_endpoints_send_json_bodies(mock_api):
    chat = CopilotChatCompletions(messages=[{"role": "user", "content": "Weather?"}], timeout=20)
    [result] = scrape([chat], tqdm_disable=True)
    assert result.ok
    [call] = mock_api.scrape_calls
    assert (call.method, call.url.path, dict(call.url.params)) == ("POST", chat.path, {})
    assert json.loads(call.content) == {
        "timeout": 20.0,
        "messages": [{"role": "user", "content": "Weather?"}],
    }


def test_get_and_post_endpoints_mix_in_one_batch(mock_api):
    import asyncio

    items = [
        {"endpoint": "walmart_search", "query": "tv", "page": 2},
        WebScreenshot(url="https://example.com"),
    ]
    results = asyncio.run(ascrape(items, tqdm_disable=True))
    assert all(result.ok for result in results)
    calls = {call.url.path: call for call in mock_api.scrape_calls}
    assert calls["/api/walmart/search"].method == "GET"
    assert dict(calls["/api/walmart/search"].url.params) == {"query": "tv", "page": "2"}
    assert calls["/api/web/screenshot"].method == "POST"
    assert json.loads(calls["/api/web/screenshot"].content) == {"url": "https://example.com"}
