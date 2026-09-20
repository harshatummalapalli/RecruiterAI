"""Regression matrix for the Search Translator — the architectural fix from
the forensic investigation into why Living Brief confirmation and executed
search behavior diverged. These are unit tests against directly-constructed
IntakeResult objects (fast, deterministic, no LLM/API cost) covering the
class of problem across varied role shapes, plus explicit named regressions
for the exact failure modes found live."""

from backend.models.intake import (
    CapabilityItem,
    ExplicitConstraints,
    FieldValue,
    FinalSearchIntentDraft,
    IntakeDecision,
    IntakeResult,
    LocationEntry,
    RoleUnderstanding,
)
from backend.services.search_translator import (
    build_confirmed_hiring_intent,
    normalize_candidate_identity,
    to_search_intent,
    translate,
)


def _result(
    identity: str,
    posted_title: str | None = None,
    locations=None,
    core=None,
    supporting=None,
    differentiators=None,
    nl_query: str = "A role description.",
    seniority: str | None = "Senior",
    exclusions=None,
) -> IntakeResult:
    return IntakeResult(
        raw_input="irrelevant for these tests",
        role_understanding=RoleUnderstanding(
            posted_title=posted_title or identity,
            primary_candidate_identity=FieldValue(value=identity, source="explicit"),
            seniority_scope=FieldValue(value=seniority),
            core_capabilities=[CapabilityItem(value=v, tier_signal="required") for v in (core or [])],
            explicit_constraints=ExplicitConstraints(
                locations=locations or [],
                exclusions=exclusions or [],
            ),
        ),
        decision=IntakeDecision(
            issues=[],
            final_search_intent=FinalSearchIntentDraft(
                hard_requirements=core or [],
                strong_signals=supporting or [],
                preferred_differentiators=differentiators or [],
                natural_language_search_query=nl_query,
            ),
        ),
        status="ready",
    )


# ---------------------------------------------------------------------------
# D — location must never become free text
# ---------------------------------------------------------------------------


def test_structured_location_reaches_search_intent_cleanly() -> None:
    result = _result(
        "Backend Engineer",
        locations=[LocationEntry(city="New York", state="NY", country="United States")],
    )
    intent = translate(result)
    assert intent.location.cities == ["New York"]
    assert intent.location.states == ["New York"]
    assert intent.location.countries == ["United States"]
    # No entry is ever a sentence containing work-mode/commute language.
    for city in intent.location.cities:
        assert "hybrid" not in city.lower()
        assert "remote" not in city.lower()
        assert "," not in city


def test_multiple_locations_stay_separate_structured_entries() -> None:
    result = _result(
        "Backend Engineer",
        locations=[
            LocationEntry(city="New York", state="NY", country="United States"),
            LocationEntry(city="Austin", state="TX", country="United States"),
        ],
    )
    intent = translate(result)
    assert intent.location.cities == ["New York", "Austin"]
    assert intent.location.states == ["New York", "Texas"]


def test_free_text_location_prose_can_never_reach_city_field_by_construction() -> None:
    """ExplicitConstraints.locations is typed as List[LocationEntry] (city/
    state/country only) — there is no code path left that can put a raw
    sentence like "New York, NY, hybrid" into a city value, unlike the old
    architecture where IntakeDecision.final_search_intent.location was a
    free string forced directly into Location.cities. This test documents
    that guarantee structurally: constructing a LocationEntry never accepts
    prose beyond what the caller explicitly puts in city/state/country."""
    # A well-behaved Task A response: the sentence has already been split at
    # the source (see prompts/intake_task_a_understanding.txt).
    result = _result(
        "Infrastructure Engineer",
        locations=[LocationEntry(city="New York", state="NY", country="United States")],
    )
    intent = translate(result)
    assert intent.location.cities == ["New York"]
    assert "hybrid" not in " ".join(intent.location.cities)
    assert "3-4 days" not in " ".join(intent.location.cities)


def test_missing_location_yields_no_filter_rather_than_a_guess() -> None:
    result = _result("Backend Engineer", locations=[])
    intent = translate(result)
    assert intent.location.cities == []
    assert intent.location.states == []


def test_state_abbreviation_is_normalized_to_full_name_regardless_of_what_task_a_returned() -> None:
    """Confirmed live: CrustData's basic_profile.location.state matches only
    the full state name — sending the two-letter abbreviation silently
    zeroes the entire result (it's ANDed with city/country). This must be
    guaranteed by code, not left to depend on the LLM following the prompt
    instruction correctly every time."""
    result = _result(
        "Backend Engineer",
        locations=[LocationEntry(city="New York", state="NY", country="United States")],
    )
    intent = translate(result)
    assert intent.location.states == ["New York"]


def test_state_full_name_passes_through_unchanged() -> None:
    result = _result(
        "Backend Engineer",
        locations=[LocationEntry(city="Austin", state="Texas", country="United States")],
    )
    intent = translate(result)
    assert intent.location.states == ["Texas"]


def test_unrecognized_state_value_passes_through_rather_than_being_dropped() -> None:
    result = _result(
        "Backend Engineer",
        locations=[LocationEntry(city="London", state=None, country="United Kingdom")],
    )
    intent = translate(result)
    assert intent.location.countries == ["United Kingdom"]
    assert intent.location.states == []


def test_single_location_gets_a_radius_anchor_for_the_opt_in_radius_search() -> None:
    result = _result(
        "Backend Engineer",
        locations=[LocationEntry(city="New York", state="NY", country="United States")],
    )
    intent = translate(result)
    # Full-name-normalized, matching the exact-match state fix above.
    assert intent.location.radius_place == "New York, New York"
    # Radius stays opt-in — exact city/state/country remains the default,
    # unchanged search behavior unless the recruiter explicitly chooses it.
    assert intent.location.radius_miles is None


def test_multiple_locations_get_no_radius_anchor() -> None:
    """A radius search means something at exactly one place — with more than
    one confirmed location there's no single anchor to offer it against."""
    result = _result(
        "Backend Engineer",
        locations=[
            LocationEntry(city="New York", state="NY", country="United States"),
            LocationEntry(city="Austin", state="TX", country="United States"),
        ],
    )
    intent = translate(result)
    assert intent.location.radius_place is None


# ---------------------------------------------------------------------------
# H — candidate identity must never be a descriptive sentence in a title filter
# ---------------------------------------------------------------------------


def test_title_shaped_identity_passes_through_unchanged() -> None:
    assert normalize_candidate_identity("Infrastructure Engineer", "Software Engineer, Infrastructure") == "Infrastructure Engineer"


def test_descriptive_identity_falls_back_to_posted_title_core() -> None:
    normalized = normalize_candidate_identity(
        "Software Engineer focused on Data Platforms",
        "Senior Software Engineer, Data Platform, AI Labs",
    )
    # First comma-delimited segment of the posted title — conservative and
    # unambiguous, unlike trying to guess how many segments are "core".
    assert normalized == "Senior Software Engineer"
    assert "focused on" not in normalized


def test_descriptive_identity_with_no_posted_title_is_truncated_not_sent_whole() -> None:
    normalized = normalize_candidate_identity(
        "A person who is responsible for building and operating the data platform end to end",
        None,
    )
    assert len(normalized.split()) <= 6


def test_normalized_identity_is_what_reaches_the_title_filter() -> None:
    result = _result(
        "Software Engineer focused on Data Platforms",
        posted_title="Senior Software Engineer, Data Platform, AI Labs",
    )
    intent = translate(result)
    assert intent.role.title == "Senior Software Engineer"
    assert "focused on" not in (intent.role.title or "")


# ---------------------------------------------------------------------------
# E, F — Core/Supporting/Differentiator signals must survive, and never as a
# fabricated exact-match skill filter
# ---------------------------------------------------------------------------


def test_tiered_signals_reach_the_natural_language_query_not_a_dead_field() -> None:
    result = _result(
        "Data Platform Engineer",
        core=["Design scalable data pipelines", "Proficiency in Python"],
        supporting=["Workflow orchestration frameworks"],
        differentiators=["Multi-region deployments"],
        nl_query="Data platform engineer with strong Python and data pipeline experience.",
    )
    intent = translate(result)
    assert "Python" in intent.natural_language_search_query
    # Never a fabricated exact-match filter — CrustDataProvider structurally
    # ignores these fields, and MatchExplainer would otherwise show every
    # candidate as "missing" every capability phrase.
    assert intent.skills.required_skills == []
    assert intent.skills.preferred_skills == []
    assert intent.ranking.must_have == []
    assert intent.ranking.nice_to_have == []


def test_tiered_signals_also_survive_as_structured_lists_for_evidence_ranking() -> None:
    result = _result(
        "Data Platform Engineer",
        core=["Proficiency in Python"],
        supporting=["Workflow orchestration frameworks"],
        differentiators=["Multi-region deployments"],
    )
    intent = translate(result)
    assert intent.core_signals == ["Proficiency in Python"]
    assert intent.supporting_signals == ["Workflow orchestration frameworks"]
    assert intent.differentiator_signals == ["Multi-region deployments"]


def test_deterministic_fallback_query_emphasizes_core_over_supporting_over_differentiators() -> None:
    result = _result(
        "Data Platform Engineer",
        core=["data pipelines", "Python"],
        supporting=["orchestration"],
        differentiators=["multi-region"],
        nl_query="",  # simulate Task B omitting it — should not happen, but must degrade safely
    )
    intent = translate(result)
    core_index = intent.natural_language_search_query.index("data pipelines")
    supporting_index = intent.natural_language_search_query.index("orchestration")
    differentiator_index = intent.natural_language_search_query.index("multi-region")
    assert core_index < supporting_index < differentiator_index


# ---------------------------------------------------------------------------
# G — title expansion happens once, through one mechanism
# ---------------------------------------------------------------------------


def test_title_expansion_runs_through_the_single_query_expansion_service() -> None:
    result = _result("Machine Learning Engineer")
    intent = to_search_intent(build_confirmed_hiring_intent(result))
    # backend/knowledge/titles.json has a real entry for this one.
    assert "ML Engineer" in intent.titles.include_titles
    assert "Applied Scientist" in intent.titles.include_titles
    # The primary identity itself never appears twice (once as role.title,
    # once duplicated inside include_titles).
    assert intent.role.title not in intent.titles.include_titles


def test_title_with_no_knowledge_entry_expands_to_nothing_conservatively() -> None:
    result = _result("Data Platform Engineer")
    intent = translate(result)
    assert intent.titles.include_titles == []


# ---------------------------------------------------------------------------
# C — confirmation blocks while unresolved (unchanged guarantee, re-verified
# against the new translator)
# ---------------------------------------------------------------------------


def test_translate_refuses_while_intake_is_not_ready() -> None:
    result = _result("Backend Engineer")
    result.status = "needs_clarification"
    try:
        translate(result)
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# K — exclusions still flow through as hard, validated constraints
# ---------------------------------------------------------------------------


def test_exclusions_reach_exclude_titles() -> None:
    result = _result("Engineering Manager", exclusions=["Director", "VP of Engineering"])
    intent = translate(result)
    assert "Director" in intent.titles.exclude_titles
    assert "VP of Engineering" in intent.titles.exclude_titles


# ---------------------------------------------------------------------------
# Role-type sweep — same assertions across varied archetypes, demonstrating
# no role-specific patch was needed (section 12/13's core ask).
# ---------------------------------------------------------------------------


def test_role_type_sweep_never_produces_free_text_location_or_sentence_titles() -> None:
    roles = [
        ("Infrastructure Engineer", "Software Engineer, Infrastructure, AI Labs"),
        ("Lead Data Analyst", "Lead Data Analyst - Cyber Incident Review"),
        ("eDiscovery Project Manager", "eDiscovery Client Services Project Manager"),
        ("Backend Engineer", "Backend Engineer"),
        ("Machine Learning Engineer", "ML/AI Engineer"),
        ("Full Stack Engineer", "Full Stack Engineer"),
        ("Frontend Engineer", "Frontend Engineer"),
    ]
    for identity, posted in roles:
        result = _result(
            identity,
            posted_title=posted,
            locations=[LocationEntry(city="New York", state="NY", country="United States")],
            core=["some required capability"],
        )
        intent = translate(result)
        assert intent.location.cities == ["New York"]
        assert len((intent.role.title or "").split()) <= 6
        assert intent.skills.required_skills == []
        assert intent.ranking.must_have == []
