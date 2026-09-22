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


# ---------------------------------------------------------------------------
# PASS 5 — Candidate Decision Card: strong_evidence and potential_concerns
# are the two fields CandidateReviewScreen.tsx renders as independent
# sections (a concern section only exists in the DOM when populated — see
# `{selectedCandidate.potentialConcerns.length ? (...) : null}`). These
# tests pin the data contract the UI relies on: evidence strength and
# requirement concerns are computed independently and neither one hides,
# empties, or overrides the other, regardless of which is strong/weak.
# ---------------------------------------------------------------------------


def test_strong_evidence_and_concern_are_both_populated_together() -> None:
    candidate = Candidate(
        name="StrongPlusConcern",
        title="Senior Backend Engineer",
        raw_data={
            "basic_profile": {"headline": "Senior Backend Engineer building Kafka pipelines"},
            "experience": {"employment_details": {"current": [{"seniority_level": "Entry Level"}]}},
        },
    )
    intent = SearchIntent(role=Role(title="Senior Backend Engineer", seniority="Senior"), core_signals=["Experience with Kafka."])

    explanation = MatchExplainer().explain(candidate, intent)

    assert len(explanation.strong_evidence) >= 1
    assert len(explanation.potential_concerns) == 1
    assert "Entry Level" in explanation.potential_concerns[0]


def test_strong_evidence_with_no_concern_produces_an_empty_concerns_list() -> None:
    # The UI's empty-container guard (`potentialConcerns.length ? ... :
    # null`) depends on this being an empty list, not a list with an empty
    # placeholder string.
    candidate = Candidate(
        name="StrongNoConcern",
        title="Senior Backend Engineer",
        raw_data={
            "basic_profile": {"headline": "Senior Backend Engineer building Kafka pipelines"},
            "experience": {"employment_details": {"current": [{"seniority_level": "Senior"}]}},
        },
    )
    intent = SearchIntent(role=Role(title="Senior Backend Engineer", seniority="Senior"), core_signals=["Experience with Kafka."])

    explanation = MatchExplainer().explain(candidate, intent)

    assert len(explanation.strong_evidence) >= 1
    assert explanation.potential_concerns == []


def test_concern_remains_visible_even_with_weak_or_no_strong_evidence() -> None:
    candidate = Candidate(
        name="WeakEvidenceConcern",
        title="Data Engineer",
        raw_data={"experience": {"employment_details": {"current": [{"seniority_level": "Entry Level"}]}}},
    )
    intent = SearchIntent(role=Role(title="Data Engineer", seniority="Senior"), core_signals=["Proficiency in Rust."])

    explanation = MatchExplainer().explain(candidate, intent)

    # No matched signal for "Rust" — evidence is effectively empty (only the
    # generic provider-fit line could appear, and it doesn't here since fit
    # wasn't returned) — but the concern must still be there regardless.
    assert not any("rust" in item.lower() for item in explanation.strong_evidence)
    assert len(explanation.potential_concerns) == 1


def test_multiple_concerns_all_remain_visible() -> None:
    # Seniority mismatch + tangential title relevance both fire as separate
    # concerns for the same candidate — both must survive into the list,
    # not just the first one found.
    candidate = Candidate(
        name="MultiConcern",
        title="Junior Marketing Coordinator",
        raw_data={"experience": {"employment_details": {"current": [{"seniority_level": "Entry Level"}]}}},
    )
    intent = SearchIntent(role=Role(title="Senior Backend Engineer", seniority="Senior"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert len(explanation.potential_concerns) == 2
    assert any("seniority" in item.lower() or "does not match" in item.lower() for item in explanation.potential_concerns)
    assert any("verifying manually" in item.lower() for item in explanation.potential_concerns)


def test_no_concern_leaves_potential_concerns_cleanly_empty() -> None:
    candidate = Candidate(
        name="CleanCandidate",
        title="Senior Data Engineer",
        raw_data={"experience": {"employment_details": {"current": [{"seniority_level": "Senior"}]}}},
    )
    intent = SearchIntent(role=Role(title="Senior Data Engineer", seniority="Senior"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.potential_concerns == []
