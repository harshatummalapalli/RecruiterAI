"""Release 1.1: exact score ties are ordered by evidence before freshness, the
score itself is untouched, and the internal ranking diagnostic explains every
position without ever reaching a recruiter."""

import pytest

from backend.models.candidate import Candidate
from backend.models.search_intent import Experience, Role, SearchIntent, Titles
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.candidate_ranker import CandidateRanker

REQ = "Proficiency in Python"


def _intent() -> SearchIntent:
    return SearchIntent(
        role=Role(title="Backend Engineer", seniority="Mid-level"),
        titles=Titles(include_titles=["Backend Engineer"]),
        experience=Experience(minimum_years=3),
        core_signals=[REQ],
    )


def _judged(name: str, source: str, strength: str, evidence_type: str, updated: str, verdict: str = "met") -> Candidate:
    judgment = {"tier": "core", "signal_text": REQ, "verdict": verdict}
    if verdict == "met":
        judgment.update(
            quote="Wrote Python services", term="Python", source=source, evidence_detail="Engineer at Acme",
            evidence_type=evidence_type, strength=strength,
        )
    return Candidate(
        candidate_id=name, name=name, title="Backend Engineer", company="Acme",
        raw_data={
            "basic_profile": {"headline": "Backend Engineer"},
            "experience": {"employment_details": {"current": [{"start_date": "2019-01-01T00:00:00"}], "past": []}},
            "metadata": {"updated_at": updated},
            "__requirement_judgments": [judgment],
        },
    )


def _demonstrated(name: str, updated: str) -> Candidate:
    return _judged(name, "harvest: employment description", "strong", "demonstrated_work", updated)


def _listed(name: str, updated: str) -> Candidate:
    return _judged(name, "harvest: skill", "supporting", "named_skill", updated)


def test_equal_scores_are_ordered_by_demonstrated_work_before_freshness() -> None:
    # The skill-only candidate has the FRESHER profile; under the old freshness-only tie-break it would win.
    listed_fresh = _listed("Listed Fresh", "2026-09-20T00:00:00+00:00")
    demonstrated_old = _demonstrated("Demonstrated Old", "2025-01-01T00:00:00+00:00")
    ranked = CandidateRanker().rank([listed_fresh, demonstrated_old], _intent())

    assert listed_fresh.final_score == pytest.approx(demonstrated_old.final_score)   # the score does not separate them
    assert [c.name for c in ranked] == ["Demonstrated Old", "Listed Fresh"]


def test_identical_evidence_still_falls_back_to_freshness_and_ties_stay_ties() -> None:
    a = _demonstrated("A", "2025-01-01T00:00:00+00:00")
    b = _demonstrated("B", "2026-09-20T00:00:00+00:00")
    ranked = CandidateRanker().rank([a, b], _intent())
    assert a.final_score == pytest.approx(b.final_score)          # genuinely indistinguishable: the tie is kept
    assert [c.name for c in ranked] == ["B", "A"]                  # freshness is a legitimate LAST tie-break


def test_the_tie_break_never_outranks_a_higher_score() -> None:
    no_evidence = _judged("None", "", "", "", "2026-09-20T00:00:00+00:00", verdict="not_evidenced")
    listed = _listed("Listed", "2020-01-01T00:00:00+00:00")
    ranked = CandidateRanker().rank([no_evidence, listed], _intent())
    assert [c.name for c in ranked] == ["Listed", "None"] and listed.final_score > no_evidence.final_score


def test_score_components_sum_to_the_score_that_ranks() -> None:
    ranker, intent = CandidateRanker(), _intent()
    candidate = _demonstrated("A", "2026-09-01T00:00:00+00:00")
    ranker.rank([candidate], intent)
    evidence = build_candidate_evidence(candidate, intent)
    components = ranker.score_components(evidence, candidate.provider_score)
    assert sum(components.values()) == pytest.approx(candidate.final_score)
    assert components["core_coverage"] == 1.0 and components["title_relevance"] == 3.0


def test_the_diagnostic_explains_each_position_and_marks_true_ties() -> None:
    ranker, intent = CandidateRanker(), _intent()
    candidates = [
        _demonstrated("D1", "2026-09-20T00:00:00+00:00"),
        _demonstrated("D2", "2025-01-01T00:00:00+00:00"),
        _listed("L1", "2026-09-25T00:00:00+00:00"),
    ]
    ordered = ranker.rank(candidates, intent)
    rows = ranker.diagnose(ordered, intent)

    assert [r["name"] for r in rows] == ["D1", "D2", "L1"]
    assert {"components", "requirements_met", "evidence_strength", "level_fit", "experience_floor", "tie_break_reason"} <= rows[0].keys()
    assert rows[0]["evidence_strength"] == {"demonstrated_work": 1, "listed_or_headline_only": 0}
    assert rows[2]["evidence_strength"] == {"demonstrated_work": 0, "listed_or_headline_only": 1}
    assert "first of the tie group" in rows[0]["tie_break_reason"]
    assert "identical evidence, ordered by profile freshness" in rows[1]["tie_break_reason"]
    assert "ordered by demonstrated-work evidence" in rows[2]["tie_break_reason"]
