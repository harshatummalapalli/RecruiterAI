from backend.models.candidate import Candidate
from backend.models.search_intent import Role, SearchIntent
from backend.services.match_explainer import MatchExplainer


def test_explainer_builds_grounded_explanation_for_a_direct_match() -> None:
    candidate = Candidate(
        name="Alicia",
        title="Senior Python Data Engineer",
        company="OpenAI",
        location="US",
        final_score=4.0,
        raw_data={
            "basic_profile": {"headline": "Senior Python Data Engineer"},
            "experience": {"employment_details": {"current": [{"seniority_level": "Senior"}]}},
            "matched_queries": ["natural_language"],
        },
    )
    intent = SearchIntent(role=Role(title="Senior Data Engineer", seniority="Senior"), core_signals=["Proficiency in Python"])

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.relevance_tier == "direct"
    assert explanation.seniority_alignment is True
    assert "aligns with the target level" in explanation.why_this_candidate
    assert any("python" in item.lower() for item in explanation.strong_evidence)
    assert any(item.startswith("Current title") or item.startswith("Headline") for item in explanation.strong_evidence)
    assert explanation.potential_concerns == []
    # Uncertainty is always explicit, never implicit.
    assert any("years of professional experience" in note for note in explanation.what_we_dont_know)


def test_explainer_never_claims_a_skill_that_was_not_literally_found() -> None:
    candidate = Candidate(name="NoEvidence", title="Data Engineer", raw_data={})
    intent = SearchIntent(role=Role(title="Data Engineer"), core_signals=["Proficiency in Python"])

    explanation = MatchExplainer().explain(candidate, intent)

    assert not any("python" in item.lower() for item in explanation.strong_evidence)
    assert not any("python" in item.lower() for item in explanation.potential_concerns)


def test_explainer_flags_seniority_mismatch_as_a_potential_concern() -> None:
    candidate = Candidate(
        name="Junior Jamie",
        title="Data Engineer",
        raw_data={"experience": {"employment_details": {"current": [{"seniority_level": "Entry Level"}]}}},
    )
    intent = SearchIntent(role=Role(title="Data Engineer", seniority="Senior"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.seniority_alignment is False
    assert any("does not align" in item.lower() or "does not match" in item.lower() for item in explanation.potential_concerns)


def test_explainer_treats_unknown_seniority_as_neither_strength_nor_concern() -> None:
    candidate = Candidate(name="Unknown Uma", title="Data Engineer", raw_data={})
    intent = SearchIntent(role=Role(title="Data Engineer", seniority="Senior"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.seniority_alignment is None
    assert not any("seniority" in item.lower() for item in explanation.potential_concerns)


def test_explainer_surfaces_provider_fit_when_present() -> None:
    candidate = Candidate(name="Fit Fiona", title="Data Engineer", raw_data={"fit": "strong"})
    intent = SearchIntent(role=Role(title="Data Engineer"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.provider_fit == "strong"
    assert any("strong relevance fit" in item.lower() for item in explanation.strong_evidence)


def test_explainer_never_leaks_internal_ranking_vocabulary_into_recruiter_text() -> None:
    candidate = Candidate(
        name="Internals",
        title="Senior Data Engineer",
        raw_data={
            "basic_profile": {"headline": "Senior Data Engineer, Python, Kubernetes"},
            "matched_queries": ["natural_language", "title_expansion"],
        },
    )
    intent = SearchIntent(
        role=Role(title="Senior Data Engineer", seniority="Senior"),
        core_signals=["Proficiency in Python."],
        supporting_signals=["Experience with Kubernetes."],
    )
    explanation = MatchExplainer().explain(candidate, intent)

    recruiter_facing_text = " ".join(
        [explanation.why_this_candidate, *explanation.strong_evidence, *explanation.potential_concerns]
    ).lower()
    # Internal ranking-weight bucket names must never appear as words in
    # recruiter-facing text, and neither should our internal discovery-query
    # strategy names.
    for internal_term in ("core signal", "supporting signal", "differentiator signal", "natural_language", "title_expansion"):
        assert internal_term not in recruiter_facing_text


def test_explainer_reports_fit_as_unavailable_rather_than_omitting_it_silently() -> None:
    candidate = Candidate(name="No Fit Data", title="Data Engineer", raw_data={})
    intent = SearchIntent(role=Role(title="Data Engineer"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.provider_fit is None
    assert any("fit" in note.lower() and "not returned" in note.lower() for note in explanation.what_we_dont_know)
