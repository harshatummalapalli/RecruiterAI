"""The NL-vs-structured retrieval experiment's own code: the structured
translator only emits verified filters, is deterministic, never expands
synonyms or invents requirements; provider order is preserved; the analysis
helpers are correct; and none of it touches production storage."""

import json
from pathlib import Path

import httpx

from backend.experiments.crustdata_retrieval.analysis import (
    fit_distribution,
    fit_position_correlation,
    overlap,
    preserves_provider_order,
    spearman,
)
from backend.experiments.crustdata_retrieval.capture import capture_first_page
from backend.experiments.crustdata_retrieval.structured import (
    VERIFIED_FILTER_FIELDS,
    build_nl_plan,
    build_structured_plan,
    payload_fields,
)
from backend.models.search_intent import Experience, Location, Role, SearchIntent, Titles
from backend.providers.crustdata import CrustDataProvider
from backend.services.search_store import SearchStore


def _intent(**overrides) -> SearchIntent:
    intent = SearchIntent(
        role=Role(title="Software Engineer", seniority="Senior", employment_type="permanent"),
        location=Location(countries=["Canada"], states=["Ontario"], cities=["Toronto"], radius_place="Toronto, ON", radius_miles=25.0, work_mode="hybrid", zip_codes=["M5V"]),
        experience=Experience(minimum_years=7),
        titles=Titles(include_titles=[], exclude_titles=["Intern"]),
        core_signals=["Proficiency in Python", "Experience with Kafka"],
        supporting_signals=["Familiarity with Docker"],
        differentiator_signals=["Exposure to AI/ML systems"],
        natural_language_search_query="Senior software engineer with Python and Kafka, Toronto.",
    )
    for key, value in overrides.items():
        setattr(intent, key, value)
    return intent


def _provider(client=None) -> CrustDataProvider:
    return CrustDataProvider(client=client)


def test_structured_payload_has_no_natural_language_clause_and_only_verified_fields() -> None:
    plan = build_structured_plan(_intent(), _provider())
    assert "search" not in plan.payload
    assert payload_fields(plan.payload) <= VERIFIED_FILTER_FIELDS
    assert "experience.employment_details.current.title" in payload_fields(plan.payload)
    assert "years_of_experience_raw" in payload_fields(plan.payload)


def test_structured_payload_is_deterministic() -> None:
    a = build_structured_plan(_intent(), _provider()).payload
    b = build_structured_plan(_intent(), _provider()).payload
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_structured_strategy_does_not_expand_title_synonyms() -> None:
    """backend/knowledge/titles.json maps "Software Engineer" -> ["Engineer", "Application Developer"]. The
    production NL path's query expander applies it; the structured strategy must not invent those titles."""
    plan = build_structured_plan(_intent(), _provider())
    assert plan.query.include_titles == ["Software Engineer"]
    assert "Application Developer" not in json.dumps(plan.payload)


def test_structured_and_nl_share_every_non_title_filter() -> None:
    intent = _intent()
    structured = build_structured_plan(intent, _provider())
    nl = build_nl_plan(intent, _provider())
    assert "search" in nl["payload"] and nl["payload"]["search"]["query"] == intent.natural_language_search_query
    title_field = "experience.employment_details.current.title"

    def non_title(payload):
        conditions = payload["filters"]["conditions"]
        return [c for c in conditions if title_field not in json.dumps(c) or c.get("type") == "(!)"]

    assert non_title(structured.payload) == non_title(nl["payload"])


def test_unsupported_work_mode_and_zip_are_not_filters_and_are_reported_unrepresented() -> None:
    plan = build_structured_plan(_intent(), _provider())
    fields = payload_fields(plan.payload)
    assert not any("work" in f or "zip" in f or "postal" in f for f in fields)
    kinds = {u["kind"] for u in plan.unrepresented}
    assert {"core_signal", "supporting_signal", "differentiator_signal", "seniority", "work_mode", "zip_codes"} <= kinds
    assert any(u["requirement"] == "Experience with Kafka" for u in plan.unrepresented)   # nothing silently dropped


def test_unverified_employment_type_is_reported_not_sent() -> None:
    plan = build_structured_plan(_intent(), _provider())
    assert "experience.employment_details.current.employment_type" not in payload_fields(plan.payload)
    assert any(u["kind"] == "employment_type" for u in plan.unrepresented)


def test_intent_without_a_title_cannot_build_a_structured_query() -> None:
    import pytest

    with pytest.raises(ValueError):
        build_structured_plan(_intent(role=Role(title=None)), _provider())


# --- provider order --------------------------------------------------------------------------------------------------
def _fake_client(items, total_count=999, cursor="cur"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"profiles": items, "total_count": total_count, "next_cursor": cursor})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _item(pid: str, name: str, fit: str = "possible") -> dict:
    return {
        "crustdata_person_id": pid,
        "basic_profile": {"name": name, "headline": "x"},
        "experience": {"employment_details": {"current": [{"title": "Engineer", "name": "Acme"}]}},
        "social_handles": {"professional_network_identifier": {"profile_url": f"https://linkedin.com/in/{pid}"}},
        "fit": fit,
    }


def test_capture_preserves_the_providers_order_and_envelope(monkeypatch) -> None:
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    items = [_item("z9", "Zed", "weak"), _item("a1", "Ada", "strong"), _item("m5", "Max", "possible")]   # deliberately not alphabetical/sorted
    provider = _provider(_fake_client(items, total_count=724204))
    capture = capture_first_page(provider, "nl", {"filters": {}}, "natural_language")

    assert [r["candidate_id"] for r in capture.rows] == ["z9", "a1", "m5"]
    assert [r["provider_position"] for r in capture.rows] == [1, 2, 3]
    assert preserves_provider_order(capture.rows)
    assert capture.total_count == 724204 and capture.next_cursor == "cur"
    assert [r["fit"] for r in capture.rows] == ["weak", "strong", "possible"]
    assert [i["crustdata_person_id"] for i in capture.raw_items] == ["z9", "a1", "m5"]
    assert "profiles" not in capture.response_envelope


def test_capture_does_not_write_search_records(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    store_dir = SearchStore().storage_dir
    before = set(Path(store_dir).glob("*.json")) if Path(store_dir).exists() else set()
    capture_first_page(_provider(_fake_client([_item("a", "A")])), "nl", {"filters": {}}, "natural_language")
    after = set(Path(store_dir).glob("*.json")) if Path(store_dir).exists() else set()
    assert before == after


# --- analysis --------------------------------------------------------------------------------------------------------
def test_overlap_metrics() -> None:
    result = overlap(["a", "b", "c", "d"], ["c", "d", "e"])
    assert result["intersection"] == 2 and result["a_only"] == 2 and result["b_only"] == 1
    assert result["jaccard"] == 0.4 and result["overlap_pct_of_a"] == 50.0
    assert overlap([], [])["jaccard"] is None


def _rows(fits):
    return [{"provider_position": i + 1, "fit": f} for i, f in enumerate(fits)]


def test_fit_distribution_by_provider_depth() -> None:
    rows = _rows(["strong", "strong", "possible", "weak", None])
    assert fit_distribution(rows, top_k=2) == {"strong": 2, "possible": 0, "weak": 0, "missing": 0}
    assert fit_distribution(rows) == {"strong": 2, "possible": 1, "weak": 1, "missing": 1}


def test_fit_position_correlation_is_descriptive_and_signed() -> None:
    assert fit_position_correlation(_rows(["strong", "strong", "possible", "possible", "weak", "weak"])) < -0.9
    assert fit_position_correlation(_rows(["weak", "weak", "possible", "possible", "strong", "strong"])) > 0.9
    assert fit_position_correlation(_rows(["possible"] * 6)) is None       # fit does not vary
    assert spearman([1, 2], [1, 2]) is None                               # too few points
