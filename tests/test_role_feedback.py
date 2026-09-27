"""Recruiter feedback: what is stored, and the small deterministic way it guides the NEXT retrieval. It never rewrites
the confirmed brief."""

import copy

from backend.models.candidate import Candidate
from backend.services import role_feedback as rf


def event(candidate_id, decision, reason=None, note=None):
    return {"candidate_id": candidate_id, "decision": decision, "feedback_reason": reason, "feedback_note": note}


def record_with(*events, decisions=None, dismissed=()):
    decisions = decisions if decisions is not None else {e["candidate_id"]: e["decision"] for e in events}
    return {"feedback_events": list(events), "recruiter_decisions": decisions, "calibration": {"dismissed": list(dismissed)}}


# ---- the reasons ----------------------------------------------------------------------------------------------------


def test_reasons_belong_to_their_decision() -> None:
    assert rf.valid_reason("maybe", "skill_not_demonstrated") and rf.valid_reason("reject", "required_technology")
    assert not rf.valid_reason("maybe", "required_technology")
    assert not rf.valid_reason("reject", "seniority_unclear")
    assert not rf.valid_reason("shortlist", "other")


def test_notes_are_short_and_single_spaced() -> None:
    assert rf.clean_note("  too   many \n spaces ") == "too many spaces"
    assert rf.clean_note("   ") is None
    assert len(rf.clean_note("x" * 900)) == rf.MAX_NOTE_CHARS


# ---- guidance: only structured, translatable reasons ---------------------------------------------------------------------


def test_reasons_become_dimensions_by_a_fixed_table() -> None:
    record = record_with(
        event("a", "reject", "required_technology"),
        event("b", "reject", "required_technology"),
        event("c", "maybe", "skill_not_demonstrated"),
        event("d", "reject", "seniority"),
        event("e", "maybe", "experience_unclear"),
        event("f", "reject", "type_of_work"),
    )
    guidance = rf.build_guidance(record)
    assert guidance.dimensions == {"technology": 3, "seniority": 1, "experience": 1, "work_type": 1}
    assert abs(sum(guidance.weights().values()) - 1.0) < 1e-9


def test_domain_career_other_and_free_text_are_stored_but_not_translated() -> None:
    record = record_with(
        event("a", "reject", "domain"),
        event("b", "reject", "career_background"),
        event("c", "reject", "other", note="wants someone from fintech, keep looking at payments people"),
        event("d", "shortlist"),
    )
    guidance = rf.build_guidance(record)
    assert guidance.empty and guidance.untranslated == 3


def test_a_decision_changed_since_no_longer_guides() -> None:
    record = record_with(event("a", "reject", "required_technology"), decisions={"a": "shortlist"})
    assert rf.build_guidance(record).empty


def test_the_latest_reason_for_a_candidate_wins() -> None:
    record = record_with(event("a", "reject", "seniority"), event("a", "reject", "required_technology"))
    assert rf.build_guidance(record).dimensions == {"technology": 1}


def test_a_dimension_the_recruiter_removed_from_the_summary_is_left_out() -> None:
    record = record_with(event("a", "reject", "required_technology"), event("b", "reject", "seniority"), dismissed=["technology"])
    assert rf.build_guidance(record).dimensions == {"seniority": 1}


# ---- guidance on evidence already read ------------------------------------------------------------------------------------


def evidence(met_core=0, floor=None, fit=None, title="direct"):
    rows = [{"tier": "core", "verdict": "met", "source": "role"} for _ in range(met_core)]
    return {"requirement_judgments": rows, "role_alignment": {"experience_floor": floor, "level_fit": fit, "title_relevance": title}}


def test_evidence_values_are_read_from_facts_already_stored() -> None:
    assert rf.evidence_value("technology", evidence(met_core=3)) == 3.0
    assert rf.evidence_value("experience", evidence(floor=False)) == -1.0
    assert rf.evidence_value("seniority", evidence(fit="aligned")) == 1.0
    assert rf.evidence_value("seniority", evidence(fit="above")) == -1.0
    assert rf.evidence_value("work_type", evidence(title="tangential")) == -1.0
    assert rf.evidence_value("technology", None) == 0.0


def test_the_guidance_score_weights_only_the_dimensions_the_recruiter_named() -> None:
    guidance = rf.Guidance({"technology": 1})
    score = rf.evidence_guidance_score(guidance)
    assert score(evidence(met_core=2, fit="above")) > score(evidence(met_core=1, fit="aligned"))
    assert rf.evidence_guidance_score(rf.Guidance())(evidence(met_core=5)) == 0.0


# ---- admission tie-break: only exact ties move ---------------------------------------------------------------------------------


def candidate(name, score):
    return Candidate(candidate_id=name, name=name, title="Engineer", company="Acme", location="", final_score=score, raw_data={})


def test_only_candidates_with_exactly_equal_baseline_scores_are_reordered() -> None:
    ranked = [candidate("top", 9.0), candidate("t1", 5.0), candidate("t2", 5.0), candidate("t3", 5.0), candidate("low", 4.0)]
    strength = {"top": 0, "t1": 0, "t2": 3, "t3": 1, "low": 99}
    result = rf.apply_admission_tie_break(ranked, rf.Guidance({"technology": 1}), lambda c, dimension: strength[c.name])
    assert [c.name for c in result] == ["top", "t2", "t3", "t1", "low"]  # ties reordered; "low" never overtakes


def test_empty_guidance_changes_nothing_at_all() -> None:
    ranked = [candidate("a", 5.0), candidate("b", 5.0), candidate("c", 5.0)]
    assert rf.apply_admission_tie_break(ranked, rf.Guidance(), lambda c, d: {"a": 0, "b": 5, "c": 9}[c.name]) == ranked


def test_the_tie_break_never_changes_a_score() -> None:
    ranked = [candidate("a", 5.0), candidate("b", 5.0)]
    before = [c.final_score for c in ranked]
    rf.apply_admission_tie_break(ranked, rf.Guidance({"seniority": 2}), lambda c, d: 1.0 if c.name == "b" else 0.0)
    assert [c.final_score for c in ranked] == before


def test_equal_guidance_keeps_the_existing_order() -> None:
    ranked = [candidate("a", 5.0), candidate("b", 5.0), candidate("c", 5.0)]
    assert rf.apply_admission_tie_break(ranked, rf.Guidance({"technology": 1}), lambda c, d: 0.0) == ranked


# ---- feedback cannot rewrite the brief -----------------------------------------------------------------------------------------


def test_guidance_has_no_way_to_touch_a_confirmed_intent() -> None:
    """Guidance is a dict of counts. The functions that use it take candidates and evidence, never an intent, and they
    return orderings, never requirements."""
    intent = {"core_signals": ["Strong Python"], "supporting_signals": ["Kafka"], "titles": {"include_titles": ["Engineer"]}}
    snapshot = copy.deepcopy(intent)
    record = record_with(event("a", "reject", "required_technology"), event("b", "reject", "seniority"))
    rf.build_guidance(record)
    rf.calibration_summary({**record, "response": {"candidates": [], "evidence": []}})
    assert intent == snapshot


# ---- the one-time summary ----------------------------------------------------------------------------------------------------


def _summary_record():
    candidates = [{"candidate_id": "a"}, {"candidate_id": "b"}]
    ev = [
        {"requirement_judgments": [{"tier": "core", "signal_text": "Distributed systems", "verdict": "not_evidenced", "source": "headline"}, {"tier": "core", "signal_text": "Python", "verdict": "met", "source": "headline"}]},
        {"requirement_judgments": [{"tier": "core", "signal_text": "Distributed systems", "verdict": "not_evidenced", "source": "headline"}]},
    ]
    record = record_with(event("a", "reject", "required_technology"), event("b", "maybe", "skill_not_demonstrated"))
    record["response"] = {"candidates": candidates, "evidence": ev}
    return record


def test_the_summary_names_the_core_requirements_the_profiles_lacked() -> None:
    summary = rf.calibration_summary(_summary_record())
    assert summary["text"] == "Got it. I'll look for stronger evidence of Distributed systems."
    assert summary["dimensions"] == ["technology"] and summary["requirements"] == ["Distributed systems"]


def test_the_summary_mentions_only_what_the_search_can_act_on() -> None:
    record = record_with(event("a", "reject", "domain"), event("b", "reject", "seniority"))
    record["response"] = {"candidates": [], "evidence": []}
    summary = rf.calibration_summary(record)
    assert summary["text"] == "Got it. I'll look for profiles closer to the level of this role."
    assert "domain" not in summary["text"].lower()


def test_with_nothing_to_act_on_the_summary_says_it_will_keep_searching_the_brief() -> None:
    record = record_with(event("a", "shortlist"), event("b", "shortlist"))
    record["response"] = {"candidates": [], "evidence": []}
    assert rf.calibration_summary(record) == {"text": "Got it. I'll keep searching against your brief.", "dimensions": [], "requirements": []}


def test_the_summary_never_ranks_or_praises() -> None:
    text = rf.calibration_summary(_summary_record())["text"].lower()
    for word in ("best", "top", "excellent", "good", "score", "rank"):
        assert word not in text.split()
