"""Which reviewed candidates are shown first, and that nobody processed is lost."""

from backend.services import candidate_presentation as cp


def judgments(*verdicts, years=True):
    rows = [{"tier": "core", "signal_text": f"Core {i}", "verdict": v, "source": "headline"} for i, v in enumerate(verdicts)]
    if years:
        rows.append({"tier": "core", "signal_text": "5+ years", "verdict": "met", "source": "career dates"})
    return {"requirement_judgments": rows}


def row(candidate_id, index, level, guidance=0.0):
    return {"id": candidate_id, "index": index, "level": level, "guidance": guidance}


# ---- the evidence level: the same fixed rule the workspace already uses ----------------------------------------------


def test_levels_follow_the_share_of_non_years_core_requirements_shown() -> None:
    assert cp.evidence_level(judgments("met", "met", "not_evidenced")) == cp.STRONG  # 2 of 3 = 67%
    assert cp.evidence_level(judgments("met", "not_evidenced", "not_evidenced")) == cp.SOME  # 1 of 3
    assert cp.evidence_level(judgments("not_evidenced", "partly")) == cp.THIN
    assert cp.evidence_level(judgments("met", "not_evidenced")) == cp.SOME  # 1 of 2 = 50%, below the 60% threshold
    # The years requirement is never one of the requirements counted.
    assert cp.evidence_level(judgments("not_evidenced", "not_evidenced")) == cp.THIN


def test_exactly_at_the_threshold_is_strong_and_below_is_some() -> None:
    assert cp.evidence_level(judgments("met", "met", "met", "not_evidenced", "not_evidenced")) == cp.STRONG  # 3/5 = 60%
    assert cp.evidence_level(judgments("met", "met", "not_evidenced", "not_evidenced", "not_evidenced")) == cp.SOME  # 2/5


def test_a_profile_that_could_not_be_checked_is_unchecked_not_thin() -> None:
    assert cp.evidence_level({}) == cp.UNCHECKED
    assert cp.evidence_level(None) == cp.UNCHECKED
    assert cp.evidence_level({"requirement_judgments": []}) == cp.UNCHECKED
    assert cp.evidence_level(judgments(years=True)) == cp.UNCHECKED  # only a years row: nothing else to check


# ---- the first five: 3 strong, 2 some, filled from what is next ------------------------------------------------------


def test_the_first_five_are_three_strong_and_two_some() -> None:
    rows = [row(f"s{i}", i, cp.STRONG) for i in range(6)] + [row(f"o{i}", 10 + i, cp.SOME) for i in range(5)] + [row("t", 20, cp.THIN)]
    chosen = cp.pick_batch(rows, cp.INITIAL_BATCH, initial=True)
    assert chosen == ["s0", "s1", "s2", "o0", "o1"]


def test_fewer_than_five_at_those_levels_fills_from_the_next_reviewed_candidates() -> None:
    rows = [row("s0", 0, cp.STRONG), row("o0", 1, cp.SOME), row("u0", 2, cp.UNCHECKED), row("t0", 3, cp.THIN), row("t1", 4, cp.THIN), row("t2", 5, cp.THIN)]
    chosen = cp.pick_batch(rows, cp.INITIAL_BATCH, initial=True)
    assert chosen == ["s0", "o0", "u0", "t0", "t1"]


def test_missing_strong_candidates_are_replaced_by_the_next_level_not_left_empty() -> None:
    rows = [row("s0", 0, cp.STRONG)] + [row(f"o{i}", 1 + i, cp.SOME) for i in range(6)]
    chosen = cp.pick_batch(rows, cp.INITIAL_BATCH, initial=True)
    assert chosen[0] == "s0" and len(chosen) == 5 and set(chosen[1:]) == {"o0", "o1", "o2", "o3"}


def test_fewer_than_five_candidates_exist() -> None:
    assert cp.pick_batch([row("a", 0, cp.SOME), row("b", 1, cp.THIN)], 5, initial=True) == ["a", "b"]
    assert cp.pick_batch([], 5, initial=True) == []


def test_within_a_level_the_order_the_search_returned_them_in_is_kept() -> None:
    rows = [row("a", 3, cp.STRONG), row("b", 1, cp.STRONG), row("c", 2, cp.STRONG)]
    assert cp.pick_batch(rows, 5, initial=True) == ["b", "c", "a"]


def test_later_batches_take_the_strongest_evidence_first() -> None:
    rows = [row("t", 0, cp.THIN), row("o", 1, cp.SOME), row("s", 2, cp.STRONG), row("u", 3, cp.UNCHECKED)]
    assert cp.pick_batch(rows, 3) == ["s", "o", "u"]


def test_feedback_guidance_only_breaks_ties_inside_a_level() -> None:
    rows = [row("a", 0, cp.STRONG, 0.0), row("b", 1, cp.STRONG, 0.9), row("c", 2, cp.SOME, 5.0)]
    # c has the highest guidance but is a lower evidence level, so it stays behind both strong candidates.
    assert cp.pick_batch(rows, 3) == ["b", "a", "c"]


# ---- what is kept ----------------------------------------------------------------------------------------------------


def _record():
    candidates = [{"candidate_id": f"c{i}"} for i in range(6)]
    evidence = [judgments("met", "met") if i < 3 else judgments("met", "not_evidenced", "not_evidenced") for i in range(6)]
    states = {f"c{i}": "review_ready" for i in range(6)}
    presentation = {f"c{i}": {"state": cp.RESERVE, "source": "initial", "seen": False} for i in range(6)}
    return {"response": {"candidates": candidates, "evidence": evidence}, "candidate_states": states, "presentation": presentation}


def test_presenting_moves_candidates_out_of_reserve_and_keeps_the_rest() -> None:
    record = _record()
    rows = cp.reserve_rows(record, lambda evidence: 0.0)
    chosen = cp.pick_batch(rows, 4, initial=True)
    cp.present(record, chosen, batch=cp.next_batch_number(record))
    counts = cp.counts(record)
    assert counts["presented"] == 4 and counts["reserve"] == 2
    # Nothing was dropped: all six are still in the record with their evidence.
    assert len(record["response"]["candidates"]) == 6 and len(record["presentation"]) == 6
    assert {e["batch"] for e in record["presentation"].values() if e["state"] == cp.PRESENTED} == {1}


def test_stale_or_unread_candidates_are_not_offered() -> None:
    record = _record()
    record["presentation"]["c0"]["stale"] = True
    record["candidate_states"]["c1"] = "building_context"
    ids = {r["id"] for r in cp.reserve_rows(record, lambda e: 0.0)}
    assert "c0" not in ids and "c1" not in ids and {"c2", "c3", "c4", "c5"} <= ids


def test_batch_numbers_increase() -> None:
    record = _record()
    cp.present(record, ["c0"], batch=cp.next_batch_number(record))
    assert cp.next_batch_number(record) == 2
