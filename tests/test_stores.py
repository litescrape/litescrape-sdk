"""Store Alpha request contracts shared with the deployed API and workbench."""

import base64
import json
from pathlib import Path

import pydantic
import pytest

from litescrape_sdk import REQUEST_TYPES, AppleAppStoreSearch, GooglePlayReviews
from litescrape_sdk.models import REQUEST_ADAPTER

SURFACES = json.loads((Path(__file__).parent / "store_contract.json").read_text(encoding="utf-8"))
CASES = [(surface, case) for surface in SURFACES for case in surface["cases"]]


@pytest.mark.parametrize("surface,case", CASES, ids=[f"{s['mode']}:{c['label']}" for s, c in CASES])
def test_store_boundary_corpus(surface, case):
    slug = surface["mode"].replace("-", "_")
    params = {"endpoint": slug, **case["params"]}
    if case["valid"]:
        request = REQUEST_ADAPTER.validate_python(params)
        assert request.path == surface["path"]
        assert "endpoint" not in request.query_params()
        assert set(request.query_params()) <= set(surface["parameters"])
    else:
        with pytest.raises(pydantic.ValidationError):
            REQUEST_ADAPTER.validate_python(params)


def test_store_fields_match_the_api():
    for surface in SURFACES:
        model = REQUEST_TYPES[surface["mode"].replace("-", "_")]
        assert set(model.model_fields) - {"endpoint"} == set(surface["parameters"])
        assert model.model_config["coerce_numbers_to_str"] is False


def test_nested_cursor_is_a_validation_error():
    token = base64.urlsafe_b64encode(("[" * 1100 + "]" * 1100).encode()).decode().rstrip("=")
    with pytest.raises(pydantic.ValidationError):
        REQUEST_ADAPTER.validate_python({"endpoint": "google_play_apps", "next_page_token": token})


def test_typed_values_and_boolean_query_serialization():
    request = AppleAppStoreSearch(term=" coffee ", country="UK", disallow_explicit=True, num=10)
    assert request.query_params()["country"] == "gb"
    assert request.query_params()["term"] == "coffee"
    assert request.query_params()["disallow_explicit"] == "true"
    assert request.query_params()["num"] == "10"
    for value in [True, False, 1.0]:
        with pytest.raises(pydantic.ValidationError):
            GooglePlayReviews(product_id="com.duolingo", num=value)
