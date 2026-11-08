from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

from brand_research.excel import export_workbook
from brand_research.models import FIELDS, NOT_ACQUIRED, UNVERIFIED, Source, safe_url
from brand_research.validation import validate_extraction, value_in_quote


def test_verified_live_cells_use_each_fields_exact_source(live_case):
    result, payload = live_case
    validate_extraction(payload, result, ownership_complete=True)
    assert result.status == "Verified"
    frame = pd.DataFrame({"Brand": [result.brand], "Category": ["Tea"]})
    data = export_workbook(frame, [result])
    book = load_workbook(BytesIO(data))
    for col, key in enumerate(FIELDS, 3):
        fact = result.facts[key]
        cell = book["Brand Research"].cell(2, col)
        assert cell.value == fact.value
        assert cell.hyperlink.target == next(
            s.url for s in result.sources if s.id == fact.evidence[0].source_id
        )
        assert fact.evidence[0].quote in cell.comment.text
        assert "FICTIONAL DEMO" not in cell.comment.text


@pytest.mark.parametrize(
    "alteration",
    ["invented_id", "invented_quote", "unsupported_value", "low_confidence", "unsafe_url"],
)
def test_ungrounded_fact_becomes_unlinked_unknown(live_case, alteration):
    result, payload = live_case
    fact = payload["facts"]["original_company"]
    if alteration == "invented_id":
        fact["evidence"][0]["source_id"] = "invented"
    elif alteration == "invented_quote":
        fact["evidence"][0]["quote"] = "Aurora Tea Company launched the brand in an invented quote."
    elif alteration == "unsupported_value":
        fact["value"] = "Wrong company"
    elif alteration == "low_confidence":
        fact["confidence"] = "low"
    else:
        result.sources[0].url = "javascript:alert(1)"
    validate_extraction(payload, result, ownership_complete=True)
    assert result.facts["original_company"].value is None
    data = export_workbook(pd.DataFrame({"Brand": ["Aurora Tea"], "Category": ["Tea"]}), [result])
    cell = load_workbook(BytesIO(data))["Brand Research"]["C2"]
    assert cell.value == UNVERIFIED
    assert cell.hyperlink is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("founding_year", 3000),
        ("founding_year", True),
        ("founding_year", "1998"),
        ("founding_year", "Not acquired"),
        ("origin_country", 1998),
    ],
)
def test_invalid_fact_types_and_years(live_case, field, value):
    result, payload = live_case
    payload["facts"][field]["value"] = value
    validate_extraction(payload, result, True)
    assert result.facts[field].value is None


@pytest.mark.parametrize("flag", ["coverage", "identity", "completed", "latest", "conflict"])
def test_uncertain_acquisitions_never_become_verified(live_case, flag):
    result, payload = live_case
    if flag == "identity":
        payload["identity_matched"] = False
    elif flag == "completed":
        payload["acquisition"]["completed"] = False
    elif flag == "latest":
        payload["acquisition"]["latest_checked"] = False
    elif flag == "conflict":
        payload["acquisition"]["conflict"] = True
    validate_extraction(payload, result, flag != "coverage")
    assert result.facts["latest_acquirer"].value is None
    assert result.facts["acquisition_year"].value is None


def test_pending_deal_rejected_even_if_model_calls_it_completed(live_case):
    result, payload = live_case
    quote = "Northstar Consumer Group agreed to acquire Aurora Tea in 2021, subject to approval."
    result.sources[1].snippet = quote
    for key in ("latest_acquirer", "acquisition_year"):
        payload["facts"][key]["evidence"][0]["quote"] = quote
    validate_extraction(payload, result, True)
    assert result.facts["latest_acquirer"].value is None
    assert result.facts["acquisition_year"].value is None


def test_different_acquisition_transactions_are_not_combined(live_case):
    result, payload = live_case
    quote = "Northstar Consumer Group acquired Aurora Tea. Another buyer completed a different acquisition in 2021."
    # Use separate exact quotes, neither tying Northstar to the 2021 transaction.
    result.sources[1].snippet = quote
    payload["facts"]["latest_acquirer"]["evidence"][0]["quote"] = (
        "Northstar Consumer Group acquired Aurora Tea."
    )
    payload["facts"]["acquisition_year"]["evidence"][0]["quote"] = (
        "Another buyer completed a different acquisition in 2021."
    )
    validate_extraction(payload, result, True)
    assert result.facts["latest_acquirer"].value is None
    assert result.facts["acquisition_year"].value is None


@pytest.mark.parametrize(
    "variant",
    [
        "adequate",
        "one_domain",
        "same_publisher",
        "silence",
        "privately_held",
        "no_coverage",
        "no_preferred",
    ],
)
def test_not_acquired_requires_explicit_independent_corroboration(live_case, variant):
    result, payload = live_case
    quote = "Aurora Tea has never been acquired and remains independently owned."
    result.sources = [
        Source("s1", "https://auroratea.example/ownership", "Ownership", quote, tier=1),
        Source("s2", "https://businesspress.example/aurora", "Independent profile", quote, tier=5),
    ]
    if variant == "same_publisher":
        result.sources[1].url = "https://news.auroratea.example/profile"
    if variant in {"silence", "privately_held"}:
        quote = "Aurora Tea is privately held with its offices in India. No ownership details are available."
        for source in result.sources:
            source.snippet = quote
    if variant == "no_preferred":
        result.sources[0].tier = 7
    refs = [{"source_id": s.id, "quote": s.snippet} for s in result.sources]
    if variant == "one_domain":
        refs = refs[:1]
    for key in ("latest_acquirer", "acquisition_year"):
        payload["facts"][key] = {"value": NOT_ACQUIRED, "confidence": "high", "evidence": refs}
    payload["acquisition"]["status"] = "not_acquired"
    validate_extraction(payload, result, variant != "no_coverage")
    for key in ("latest_acquirer", "acquisition_year"):
        assert result.facts[key].value == (NOT_ACQUIRED if variant == "adequate" else None)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/source",
        "javascript:alert(1)",
        "https://user:secret@example.com/a",
        "http://127.0.0.1/a",
        "http://localhost/a",
        "http://10.0.0.1/a",
        "https://example.com/with space",
        "https://[::1]/a",
    ],
)
def test_unsafe_source_links_rejected(url):
    assert not safe_url(url)


def test_value_matching_does_not_accept_substrings():
    assert not value_in_quote("US", "The industry was launched in 1998.")
    assert not value_in_quote(1998, "A number 19980 was mentioned.")
    assert value_in_quote("India", "Origin: India.")
