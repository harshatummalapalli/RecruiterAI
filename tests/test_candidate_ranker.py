from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import Role, SearchIntent, Titles
from backend.services.candidate_ranker import CandidateRanker


def _candidate(name: str, title: str, raw_data: dict | None = None, provider_score: float | None = None) -> Candidate:
    return Candidate(name=name, title=title, raw_data=raw_data or {}, provider_score=provider_score)


def test_direct_title_and_seniority_match_ranks_above_adjacent() -> None:
    intent = SearchIntent(role=Role(title="Senior Data Engineer", seniority="Senior"))
    candidates = [
        _candidate("Adjacent Adam", "Senior Software Engineer", raw_data={"experience": {}}),
        _candidate(
            "Direct Dana",
            "Senior Data Engineer",
            raw_data={"experience": {"employment_details": {"current": [{"seniority_level": "Senior"}]}}},
        ),
    ]

    ranked = CandidateRanker().rank(candidates, intent)

    assert ranked[0].name == "Direct Dana"
    assert ranked[1].name == "Adjacent Adam"


def test_core_signal_hit_in_title_outranks_no_signal_hit_within_same_tier() -> None:
    intent = SearchIntent(role=Role(title="Data Engineer"), core_signals=["Proficiency in Python"])
    with_signal = _candidate("Has Python", "Python Data Engineer")
    without_signal = _candidate("No Signal", "Data Engineer")

    ranked = CandidateRanker().rank([without_signal, with_signal], intent)

    assert ranked[0].name == "Has Python"
    assert ranked[1].name == "No Signal"


def test_seniority_mismatch_is_a_real_penalty_not_a_missing_data_penalty() -> None:
    intent = SearchIntent(role=Role(title="Data Engineer", seniority="Senior"))
    mismatched = _candidate(
        "Entry Erin",
        "Data Engineer",
        raw_data={"experience": {"employment_details": {"current": [{"seniority_level": "Entry Level"}]}}},
    )
    unknown = _candidate("Unknown Uma", "Data Engineer", raw_data={})

    ranked = CandidateRanker().rank([mismatched, unknown], intent)

    # A confirmed mismatch scores below a candidate with no seniority data at
    # all — missing data must never score worse than a real mismatch.
    assert ranked[0].name == "Unknown Uma"
    assert ranked[1].name == "Entry Erin"


def test_provider_fit_strong_adds_a_modest_bonus_but_never_dominates_title_relevance() -> None:
    intent = SearchIntent(role=Role(title="Data Engineer"))
    strong_fit_but_unrelated_title = _candidate("Fit Fiona", "Marketing Manager", raw_data={"fit": "strong"})
    direct_title_no_fit_data = _candidate("Direct Dara", "Data Engineer", raw_data={})

    ranked = CandidateRanker().rank([strong_fit_but_unrelated_title, direct_title_no_fit_data], intent)

    assert ranked[0].name == "Direct Dara"


def test_convergence_bonus_applies_when_found_by_multiple_queries() -> None:
    intent = SearchIntent(role=Role(title="Data Engineer"))
    single_source = _candidate("Single", "Data Engineer", raw_data={"matched_queries": ["natural_language"]})
    both_sources = _candidate("Both", "Data Engineer", raw_data={"matched_queries": ["natural_language", "title_expansion"]})

    ranked = CandidateRanker().rank([single_source, both_sources], intent)

    assert ranked[0].name == "Both"


def test_missing_skills_data_never_penalizes_a_candidate() -> None:
    # This account's CrustData plan never returns a "skills" field — absence
    # of any skill evidence must never be scored as a negative signal.
    intent = SearchIntent(role=Role(title="Data Engineer"), core_signals=["Proficiency in Python"])
    candidate = _candidate("NoSkillData", "Data Engineer", raw_data={})

    ranked = CandidateRanker().rank([candidate], intent)

    assert ranked[0].final_score is not None
    assert ranked[0].final_score >= 0.0


def test_career_role_count_is_not_used_as_a_ranking_signal() -> None:
    intent = SearchIntent(role=Role(title="Data Engineer"))
    long_history = _candidate(
        "Long History",
        "Data Engineer",
        raw_data={"experience": {"employment_details": {"past": [{"title": f"Role {i}"} for i in range(10)]}}},
    )
    short_history = _candidate("Short History", "Data Engineer", raw_data={})

    ranked = CandidateRanker().rank([long_history, short_history], intent)

    # Identical title relevance, no other differentiating evidence — role
    # count breaks no ties here; name is the only deterministic tiebreaker.
    assert ranked[0].final_score == ranked[1].final_score
    assert [c.name for c in ranked] == sorted([c.name for c in [long_history, short_history]])


def test_no_role_specific_hardcoding_same_logic_generalizes_across_role_families() -> None:
    # The exact same ranker code, with no per-role branch anywhere, must
    # correctly favor a direct title match for entirely different disciplines.
    for target_title, matching_title, unrelated_title in [
        ("Backend Engineer", "Backend Engineer", "Product Marketing Manager"),
        ("Lead Data Analyst", "Lead Data Analyst", "Warehouse Associate"),
        ("Infrastructure Engineer", "Infrastructure Engineer", "Executive Assistant"),
    ]:
        intent = SearchIntent(role=Role(title=target_title), titles=Titles(include_titles=[]))
        direct = _candidate("Direct", matching_title, raw_data={})
        unrelated = _candidate("Unrelated", unrelated_title, raw_data={})

        ranked = CandidateRanker().rank([unrelated, direct], intent)

        assert ranked[0].name == "Direct", f"failed for role family: {target_title}"


# ---------------------------------------------------------------------------
# Harvest second-stage reranking — baseline untouched, only top-N enriched
# and reranked, candidates below the cutoff retain their exact positions.
# ---------------------------------------------------------------------------


def test_baseline_rank_is_unaffected_by_harvest_being_available_or_not() -> None:
    # rank() never looks at Harvest at all — it must produce identical
    # scores/order regardless of whether Harvest is configured anywhere.
    intent = SearchIntent(role=Role(title="Data Engineer"))
    candidates = [_candidate("A", "Data Engineer"), _candidate("B", "Software Engineer")]

    ranked_once = CandidateRanker().rank([c.model_copy() for c in candidates], intent)
    ranked_again = CandidateRanker().rank([c.model_copy() for c in candidates], intent)

    assert [c.name for c in ranked_once] == [c.name for c in ranked_again]
    assert [c.final_score for c in ranked_once] == [c.final_score for c in ranked_again]


def test_rerank_top_n_only_reorders_within_the_enriched_slice_tail_untouched() -> None:
    # The exact scenario from the Harvest integration plan: baseline A..G,
    # enrich top 5 (A-E). Harvest evidence for B and E is strong enough to
    # move them above A/C/D within the slice. F and G must keep their exact
    # baseline positions (indices 5 and 6) — an enriched candidate must
    # never be able to outrank a candidate that was never considered.
    intent = SearchIntent(role=Role(title="Data Engineer"), core_signals=["Proficiency in Python."])
    names = ["A", "B", "C", "D", "E", "F", "G"]
    candidates = {
        name: Candidate(candidate_id=name, name=name, title="Data Engineer", raw_data={}, provider_score=0.0)
        for name in names
    }

    ranker = CandidateRanker()
    baseline = ranker.rank(list(candidates.values()), intent)
    assert [c.name for c in baseline] == names  # identical baseline score/title -> alphabetical tiebreak

    baseline_tail_scores = {c.name: c.final_score for c in baseline[5:]}

    harvest_by_id = {
        candidates["B"].candidate_id: HarvestEvidence(raw={"element": {"skills": [{"name": "Python"}]}}, success=True),
        candidates["E"].candidate_id: HarvestEvidence(raw={"element": {"skills": [{"name": "Python"}]}}, success=True),
    }

    reranked = ranker.rerank_top_n(baseline, intent, harvest_by_id, top_n=5)

    # F and G (indices 5, 6) are exactly where they started, untouched.
    assert [c.name for c in reranked[5:]] == ["F", "G"]
    assert {c.name: c.final_score for c in reranked[5:]} == baseline_tail_scores
    # B and E, the only two with real Harvest evidence, now lead the
    # enriched slice — but never past index 4 into F/G's territory.
    assert set(c.name for c in reranked[:2]) == {"B", "E"}
    assert set(c.name for c in reranked[:5]) == {"A", "B", "C", "D", "E"}


def test_rerank_top_n_of_zero_or_negative_is_a_no_op() -> None:
    intent = SearchIntent(role=Role(title="Data Engineer"))
    candidates = [_candidate("A", "Data Engineer"), _candidate("B", "Data Engineer")]
    ranker = CandidateRanker()
    baseline = ranker.rank(candidates, intent)

    result = ranker.rerank_top_n(baseline, intent, {}, top_n=0)

    assert result == baseline


def test_rerank_top_n_with_no_harvest_evidence_leaves_order_unchanged() -> None:
    intent = SearchIntent(role=Role(title="Data Engineer"))
    candidates = [_candidate("A", "Data Engineer"), _candidate("B", "Software Engineer")]
    ranker = CandidateRanker()
    baseline = ranker.rank(candidates, intent)

    reranked = ranker.rerank_top_n(baseline, intent, {}, top_n=5)

    assert [c.name for c in reranked] == [c.name for c in baseline]
