"""Phase 1 — capability map + routing-rule tests."""

from backend.services import crustdata_capabilities as cap


def test_unknown_field_defaults_to_unverified_and_never_hard_filters() -> None:
    c = cap.get("some.unlisted.field")
    assert c.filter_status == cap.FILTER_UNVERIFIED
    allowed, _ = cap.can_hard_filter("some.unlisted.field")
    assert allowed is False


def test_unavailable_field_never_hard_filters() -> None:
    allowed, _ = cap.can_hard_filter("skills.professional_network_skills")
    assert allowed is False
    # skills are verifiable via Harvest -> route to the judge, not disclose
    assert cap.recommend_routing("skills.professional_network_skills", "required") == "judge"


def test_work_mode_cannot_enforce_or_verify_so_disclose() -> None:
    assert cap.recommend_routing("work_mode", "required") == "disclose"


def test_verified_high_confidence_required_enforces() -> None:
    allowed, warn = cap.can_hard_filter("years_of_experience_raw")
    assert allowed is True and warn is None
    assert cap.recommend_routing("years_of_experience_raw", "required") == "enforce"
    assert cap.recommend_routing("experience.employment_details.current.title", "required") == "enforce"


def test_verified_but_unknown_confidence_still_usable_with_warning() -> None:
    # The agreed refinement: data_confidence=unknown must NOT make a verified
    # filter unusable. Headcount is verified-but-unknown and RETURNED.
    allowed, warn = cap.can_hard_filter("experience.employment_details.current.company_headcount_latest")
    assert allowed is True
    assert warn is not None  # completeness warning attached
    assert cap.recommend_routing("experience.employment_details.current.company_headcount_latest", "required") == "enforce_with_warning"


def test_response_gated_verified_field_is_enforce_but_not_verifiable() -> None:
    # education stream: filterable server-side, returned blank.
    assert cap.recommend_routing("education.schools.field_of_study", "required") == "enforce_but_not_verifiable"
    assert cap.is_displayable("education.schools.field_of_study") is False
    # description keyword retrieval: same shape.
    assert cap.recommend_routing("experience.employment_details.current.description", "required") == "enforce_but_not_verifiable"
    assert cap.is_displayable("basic_profile.headline") is True


def test_preferred_company_does_not_fabricate_a_provider_boost() -> None:
    # The Epiq lesson encoded: no verified preference mechanism -> context/evidence,
    # never a pretend NL boost.
    assert cap.PREFERENCE_MECHANISM_AVAILABLE is False
    assert cap.recommend_routing("experience.employment_details.current.company_name", "preferred") == "context_or_evidence"


def test_fuzzy_is_whole_word_flag_is_set() -> None:
    assert cap.FUZZY_IS_WHOLE_WORD is True
