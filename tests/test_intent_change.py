"""A change is meaningful only when it alters what is searched or how it is checked."""

import copy

from backend.services.intent_change import meaningful_changes

BASE = {
    "role": {"title": "Backend Engineer", "seniority": "Senior", "employment_type": None},
    "location": {"countries": ["Canada"], "states": ["Ontario"], "cities": ["Toronto"], "radius_miles": 25, "radius_place": "Toronto, Ontario", "work_mode": "hybrid"},
    "experience": {"minimum_years": 5, "maximum_years": 10},
    "titles": {"include_titles": ["Backend Engineer", "Software Engineer"], "exclude_titles": []},
    "skills": {"required_skills": ["Python"], "preferred_skills": []},
    "company_preferences": {"exclude_current_companies": ["Acme"], "preferred_company_types": []},
    "previous_background": {"preferred_companies": []},
    "core_signals": ["Strong Python", "Event-driven systems"],
    "supporting_signals": ["Kafka"],
    "differentiator_signals": ["Snowflake"],
    "natural_language_search_query": "Senior backend engineer",
}


def changed(**edits):
    intent = copy.deepcopy(BASE)
    for path, value in edits.items():
        node = intent
        *parents, leaf = path.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return meaningful_changes(BASE, intent)


def test_identical_intents_have_no_change() -> None:
    assert meaningful_changes(BASE, copy.deepcopy(BASE)) == []


def test_moving_a_requirement_between_tiers_is_meaningful() -> None:
    assert changed(core_signals=["Strong Python"], supporting_signals=["Kafka", "Event-driven systems"]) == ["core requirements", "supporting requirements"]


def test_adding_or_removing_a_required_technology_is_meaningful() -> None:
    assert changed(skills__required_skills=["Python", "Go"]) == ["skills"]
    assert changed(core_signals=["Strong Python", "Event-driven systems", "Rust"]) == ["core requirements"]


def test_experience_title_location_and_exclusions_are_meaningful() -> None:
    assert changed(experience__minimum_years=8) == ["experience"]
    assert changed(titles__include_titles=["Backend Engineer"]) == ["title family"]
    assert changed(location__cities=["Ottawa"]) == ["location or work mode"]
    assert changed(location__work_mode="remote") == ["location or work mode"]
    assert changed(company_preferences__exclude_current_companies=[]) == ["company preferences or exclusions"]
    assert changed(role__title="Data Engineer") == ["role or level"]


def test_wording_case_spacing_and_punctuation_are_not_meaningful() -> None:
    assert changed(core_signals=["strong python.", "  Event-driven   systems"]) == []
    assert changed(role__title="backend  engineer") == []


def test_order_of_set_like_lists_is_not_meaningful() -> None:
    assert changed(titles__include_titles=["Software Engineer", "Backend Engineer"]) == []
    assert changed(core_signals=["Event-driven systems", "Strong Python"]) == []


def test_the_model_written_search_sentence_is_not_a_recruiter_decision() -> None:
    assert changed(natural_language_search_query="A completely different sentence") == []
