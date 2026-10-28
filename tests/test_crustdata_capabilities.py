"""The capability model is the live source of truth for which recruiter-intent
filters may become hard CrustData filters. These tests pin that the derived
whitelist is model-driven and honest — it includes only verified-filterable
fields and excludes anything the model cannot vouch for."""

from backend.services import crustdata_capabilities as cap
from backend.services.crustdata_capabilities import (
    FILTER_FIELD_MAP,
    can_hard_filter,
    supported_search_query_filters,
)


def test_supported_filters_are_exactly_the_verified_ones() -> None:
    supported = supported_search_query_filters()
    # Every returned filter maps to a field the model says is hard-filterable.
    for name in supported:
        assert can_hard_filter(FILTER_FIELD_MAP[name])[0], name
    # Every filter left out maps to a field the model will NOT vouch for.
    for name, field in FILTER_FIELD_MAP.items():
        if name not in supported:
            assert not can_hard_filter(field)[0], name


def test_known_hard_filters_present_and_unverified_fields_absent() -> None:
    supported = set(supported_search_query_filters())
    # Genuinely verified -> present.
    for name in ("include_titles", "cities", "minimum_years", "employment_type",
                 "exclude_current_companies", "preferred_companies_ever",
                 "must_have_keywords", "must_have_keyword_groups"):
        assert name in supported
    # Never-probed or unavailable -> absent (so never silently enforced).
    assert "preferred_company_types" not in supported  # company_type not in the map
    assert "required_skills" not in supported           # skills list unavailable
    assert "preferred_skills" not in supported
    assert "work_mode" not in supported                 # unavailable on person_search
    assert "zip_codes" not in supported                 # no CrustData field


def test_whitelist_tracks_the_model_not_a_hardcoded_list() -> None:
    # Flip a mapped field to unavailable -> it drops out of the derived list;
    # restore it -> it returns. Proves the list is computed from the model.
    field = FILTER_FIELD_MAP["cities"]
    original = cap._MAP.get(field)
    try:
        cap._MAP[field] = cap._c(field, cap.FILTER_UNAVAILABLE, cap.RESP_RETURNED, cap.CONF_UNKNOWN, False)
        assert "cities" not in supported_search_query_filters()
    finally:
        if original is not None:
            cap._MAP[field] = original
    assert "cities" in supported_search_query_filters()


def test_api_whitelist_is_the_derived_list() -> None:
    from backend.api import CRUSTDATA_SUPPORTED_FILTERS
    assert CRUSTDATA_SUPPORTED_FILTERS == supported_search_query_filters()
