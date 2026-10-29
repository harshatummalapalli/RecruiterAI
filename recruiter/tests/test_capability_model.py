"""The shared CrustData capability model — the router both Intake and Briefing read."""

from recruiter.providers import capability_model as cap


def test_supported_filters_include_the_verified_ones():
    supported = set(cap.supported_filters())
    assert {"minimum_years", "cities", "countries", "exclude_current_companies"} <= supported
    # work_mode and the skills list are never hard filters.
    assert "work_mode" not in supported


def test_work_mode_routes_to_disclose():
    assert cap.route_filter("work_mode") == cap.DISCLOSE


def test_years_and_location_enforce():
    assert cap.route_filter("minimum_years") == cap.ENFORCE
    assert cap.route_filter("cities") == cap.ENFORCE


def test_capability_keyword_group_enforces_via_headline():
    assert cap.route_filter("must_have_keyword_groups") == cap.ENFORCE


def test_preferred_strength_never_hard_enforces():
    # A verified field asked as a 'preferred' signal gets context/evidence, not a filter.
    assert cap.route_filter("cities", "preferred") == cap.CONTEXT


def test_unknown_field_is_not_silently_enforced():
    assert cap.route_filter("some_made_up_filter") == cap.JUDGE
