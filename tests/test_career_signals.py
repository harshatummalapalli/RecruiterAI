# Regression tests for the three search-semantics bugs the Search Logic
# Experiment surfaced: unknown company size silently reading as "small",
# industry aggregated across a whole career instead of scoped to one
# employment event, and "reached leadership once" conflated with "currently
# a leader." See backend/services/career_signals.py's module docstring.

from backend.services.career_signals import (
    current_employer_matches_industry,
    current_role,
    currently_in_leadership,
    currently_leads_at_industry,
    ever_matches_industry,
    event_matches_industry,
    historical_leadership_progression,
    is_enterprise_company,
    is_small_company,
    known_headcount,
    worked_across_size_bands,
    years_in_industry,
)

TECH = ["technology", "software", "it services", "internet"]


def _role(title, headcount=None, industries=None, start=None, end=None, network_industry=None, duration=None):
    event = {"title": title, "company_headcount_latest": headcount, "start_date": start, "end_date": end}
    if industries is not None:
        event["company_industries"] = industries
    if network_industry is not None:
        event["company_professional_network_industry"] = network_industry
    if duration is not None:
        event["duration_years"] = duration
    return event


# ---------------------------------------------------------------------------
# 1. Company size — unknown must never match
# ---------------------------------------------------------------------------

def test_known_headcount_rejects_zero_null_missing_malformed():
    assert known_headcount(0) is None
    assert known_headcount(None) is None
    assert known_headcount({}) is None  # missing key upstream is handled by callers passing None
    assert known_headcount("5000") is None  # malformed: a string, never coerced
    assert known_headcount(-50) is None
    assert known_headcount(True) is None  # bool must never read as 1
    assert known_headcount(150) == 150.0


def test_small_company_boundary_values():
    assert is_small_company(150) is True
    assert is_small_company(200) is True   # inclusive boundary
    assert is_small_company(201) is False
    assert is_small_company(0) is False    # UNKNOWN, not "tiny"
    assert is_small_company(None) is False


def test_enterprise_company_boundary_values():
    assert is_enterprise_company(5000) is True   # inclusive boundary
    assert is_enterprise_company(6000) is True
    assert is_enterprise_company(4999) is False
    assert is_enterprise_company(0) is False     # UNKNOWN, not "huge"
    assert is_enterprise_company(None) is False


def test_worked_across_size_bands_with_mixed_known_and_unknown_history():
    events = [
        _role("Recruiter", headcount=0),        # UNKNOWN — contributes nothing
        _role("Recruiter", headcount=None),     # UNKNOWN — contributes nothing
        _role("Recruiter", headcount=150),       # known small
        _role("Recruiter", headcount=22000),     # known enterprise
    ]
    assert worked_across_size_bands(events) is True


def test_worked_across_size_bands_false_when_only_unknowns_look_small():
    # The exact false-positive pattern the experiment found: a candidate
    # whose only "small" evidence was a headcount of 0 must NOT pass.
    events = [
        _role("Recruiter", headcount=0),
        _role("Recruiter", headcount=29908),  # known enterprise
    ]
    assert worked_across_size_bands(events) is False


def test_worked_across_size_bands_requires_both_bands_known():
    only_small = [_role("Recruiter", headcount=100)]
    only_enterprise = [_role("Recruiter", headcount=50000)]
    assert worked_across_size_bands(only_small) is False
    assert worked_across_size_bands(only_enterprise) is False


# ---------------------------------------------------------------------------
# 2. Industry — scoped to the employment event a requirement refers to
# ---------------------------------------------------------------------------

def test_A_current_tech_company():
    events = [_role("Talent Acquisition Lead", industries=["Software Development"], end=None)]
    assert current_employer_matches_industry(events, TECH) is True


def test_B_current_non_tech_plus_historical_tech_does_not_satisfy_current_scope():
    # The ACTUAL regression case discovered in the Search Logic Experiment:
    # Harsha T.'s current employer (Epiq) is Law Practice/Legal Services;
    # only a PAST employer was tech-classified. Under the pre-fix,
    # career-wide aggregation this incorrectly satisfied a "currently at a
    # technology company" check.
    events = [
        _role("Talent Acquisition Lead", industries=["Law Practice", "Legal Services"], end=None),  # current
        _role("Talent Delivery Manager", industries=["Business Consulting and Services"], end="2025-03-01"),
        _role("Senior Manager Talent Acquisition", industries=["Technology, Information and Internet"], end="2022-04-01"),
    ]
    assert current_employer_matches_industry(events, TECH) is False
    assert ever_matches_industry(events, TECH) is True  # unscoped "worked at" is still True


def test_C_historical_tech_requirement_any_single_past_event_qualifies():
    events = [
        _role("Recruiter", industries=["Legal Services"], end=None),
        _role("Recruiter", industries=["Software Development"], end="2020-01-01"),
    ]
    assert ever_matches_industry(events, TECH) is True


def test_D_multiple_employers_mixed_industries_years_only_counts_matching_ones():
    events = [
        _role("Recruiter", industries=["Software Development"], duration=2.0, end="2022-01-01"),
        _role("Recruiter", industries=["Legal Services"], duration=3.0, end="2019-01-01"),
        _role("Recruiter", industries=["Technology, Information and Internet"], duration=1.5, end="2024-01-01"),
    ]
    assert years_in_industry(events, TECH) == 3.5  # only the two tech-classified events


def test_E_missing_industry_never_matches_and_never_crashes():
    events = [_role("Recruiter", industries=None, end=None), {"title": "Recruiter", "end_date": None}]
    assert current_employer_matches_industry(events, TECH) is False
    assert ever_matches_industry(events, TECH) is False
    assert years_in_industry(events, TECH) == 0.0


def test_F_current_company_only_language_ignores_past_entirely_even_when_richer():
    events = [
        _role("Recruiter", industries=["Healthcare"], end=None),  # current, not tech
        _role("Recruiter", industries=["Software Development", "Internet", "Technology"], end="2018-01-01"),
    ]
    assert current_employer_matches_industry(events, TECH) is False


def test_G_current_role_and_current_company_industry_combined():
    events = [
        _role("Talent Acquisition Lead", industries=["Software Development"], end=None),
        _role("Recruiter", industries=["Legal Services"], end="2019-01-01"),
    ]
    assert currently_leads_at_industry(events, TECH) is True


def test_single_event_helper_is_scoped_to_that_event_only():
    tech_event = _role("Recruiter", industries=["Software Development"])
    other_event = _role("Recruiter", industries=["Legal Services"])
    assert event_matches_industry(tech_event, TECH) is True
    assert event_matches_industry(other_event, TECH) is False


# ---------------------------------------------------------------------------
# 3. Career progression — current state vs. history
# ---------------------------------------------------------------------------

def test_A_recruiter_manager_director_is_historical_progression():
    events = [
        _role("Recruiter", start="2016-01-01", end="2018-01-01"),
        _role("Recruiting Manager", start="2018-01-01", end="2020-01-01"),
        _role("Director of Talent Acquisition", start="2020-01-01", end=None),
    ]
    assert historical_leadership_progression(events) is True
    assert currently_in_leadership(events) is True  # current role is also leadership here


def test_B_recruiter_manager_ic_history_true_but_currently_false():
    # The ACTUAL regression case from the experiment: Brian Van Vooren
    # reached Director, then later moved to the IC-sounding "Executive
    # Recruiter" title. Historical progression happened; current state
    # is not leadership.
    events = [
        _role("Recruiter", start="1996-01-01", end="2004-07-01"),
        _role("Talent Acquisition Advisor and Team Lead", start="2004-07-01", end="2010-04-01"),
        _role("Director of Talent Acquisition", start="2018-03-01", end="2019-06-01"),
        _role("Executive Recruiter", start="2019-06-01", end=None),  # current — IC-shaped
    ]
    assert historical_leadership_progression(events) is True
    assert currently_in_leadership(events) is False


def test_C_recruiter_director_ic_same_pattern_shorter_history():
    events = [
        _role("Recruiter", start="2015-01-01", end="2018-01-01"),
        _role("Director of Recruiting", start="2018-01-01", end="2021-01-01"),
        _role("Recruiting Coordinator", start="2021-01-01", end=None),  # current — IC
    ]
    assert historical_leadership_progression(events) is True
    assert currently_in_leadership(events) is False


def test_D_recruiter_manager_director_head_progression_and_current_both_true():
    events = [
        _role("Recruiter", start="2010-01-01", end="2013-01-01"),
        _role("Recruiting Manager", start="2013-01-01", end="2016-01-01"),
        _role("Director of Talent Acquisition", start="2016-01-01", end="2020-01-01"),
        _role("Head of Talent Acquisition", start="2020-01-01", end=None),
    ]
    assert historical_leadership_progression(events) is True
    assert currently_in_leadership(events) is True


def test_E_ambiguous_current_title_does_not_crash_and_reads_as_not_leadership():
    # A title that matches neither the leadership nor IC vocabulary at all
    # (e.g. a non-recruiting title reached via an internal transfer).
    events = [
        _role("Recruiter", start="2015-01-01", end="2018-01-01"),
        _role("Program Coordinator", start="2018-01-01", end=None),
    ]
    assert currently_in_leadership(events) is False


def test_F_missing_current_title_is_handled_without_crashing():
    events = [
        _role("Recruiter", start="2015-01-01", end="2018-01-01"),
        {"title": None, "start_date": "2018-01-01", "end_date": None},
    ]
    assert currently_in_leadership(events) is False
    assert current_role(events)["start_date"] == "2018-01-01"


def test_G_current_leadership_with_earlier_ic_history_both_true():
    events = [
        _role("Recruiter", start="2016-01-01", end="2018-10-01"),
        _role("Recruiting Manager", start="2018-10-01", end=None),
    ]
    assert historical_leadership_progression(events) is True
    assert currently_in_leadership(events) is True


def test_no_ic_role_ever_means_no_historical_progression_even_with_leadership():
    # A candidate who was always in a leadership-shaped title never shows
    # "progression" by this definition — there is no earlier IC state to
    # progress from.
    events = [_role("Recruiting Manager", start="2016-01-01", end=None)]
    assert historical_leadership_progression(events) is False


def test_empty_history_is_handled_without_crashing():
    assert historical_leadership_progression([]) is False
    assert currently_in_leadership([]) is False
    assert current_role([]) is None
