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
    # The seniority sentence is the evidence-cited basis, not a restatement of a provider label.
    assert "directly names the target seniority" in explanation.why_this_candidate
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


def test_explainer_keeps_provider_fit_internal_never_in_recruiter_facing_text() -> None:
    # PASS 6 (product pass, section 8/11): provider_fit is preserved as
    # internal/debug data (the field itself), but must never phrase into a
    # recruiter-facing bullet — the recruiter should never see language that
    # implies a search provider made the call ("flagged by the provider").
    candidate = Candidate(name="Fit Fiona", title="Data Engineer", raw_data={"fit": "strong"})
    intent = SearchIntent(role=Role(title="Data Engineer"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.provider_fit == "strong"
    recruiter_facing_text = " ".join([explanation.why_this_candidate, *explanation.strong_evidence, *explanation.potential_concerns]).lower()
    for banned_term in ("provider", "flagged", "relevance fit"):
        assert banned_term not in recruiter_facing_text


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
    # strategy names or provider/enrichment plumbing (PASS 6, section 11 —
    # the recruiter experiences "RecruiterAI researched these candidates,"
    # never which provider or enrichment stage supplied what).
    for internal_term in (
        "core signal", "supporting signal", "differentiator signal", "natural_language", "title_expansion",
        "crustdata", "harvest", "apify", "provider", "enrichment", "enriched",
    ):
        assert internal_term not in recruiter_facing_text


def test_missing_provider_fit_is_not_surfaced_as_an_unknown_to_recruiters() -> None:
    # Release 1: "the search's relevance signal (fit) was not returned" is
    # internal plumbing a recruiter cannot act on, so it no longer appears in
    # What We Don't Know. provider_fit stays None on the explanation itself.
    candidate = Candidate(name="No Fit Data", title="Data Engineer", raw_data={})
    intent = SearchIntent(role=Role(title="Data Engineer"))

    explanation = MatchExplainer().explain(candidate, intent)

    assert explanation.provider_fit is None
    assert not any("fit" in note.lower() for note in explanation.what_we_dont_know)


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
    # Target seniority is "Lead" (not "Senior") so the candidate's own title
    # text doesn't happen to name it — this is what lets the provider's
    # "Entry Level" field legitimately produce a concern under the PASS 6
    # evidence-based seniority rule (see test_classify_seniority_* below for
    # the direct coverage of that rule itself).
    candidate = Candidate(
        name="StrongPlusConcern",
        title="Senior Backend Engineer",
        raw_data={
            "basic_profile": {"headline": "Senior Backend Engineer building Kafka pipelines"},
            "experience": {"employment_details": {"current": [{"seniority_level": "Entry Level"}]}},
        },
    )
    intent = SearchIntent(role=Role(title="Senior Backend Engineer", seniority="Lead"), core_signals=["Experience with Kafka."])

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
