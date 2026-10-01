"""Phase 1a eligibility-gate regression harness.

This is the permanent, labelled multi-JD fixture set the architecture-hardening
plan requires before (and after) any admission/ranking change. Each fixture in
tests/fixtures/admission_regression/ is one JD with a frozen pool of candidate
signal tuples (level_fit, experience_floor) and a human-reviewable expected
verdict per candidate. Freezing the signals — rather than re-running live
CrustData retrieval — is deliberate: it isolates the eligibility gate as the
only variable, so a verdict change is attributable to the gate and nothing
else, and the run is free and repeatable.

The Epiq fixture is real (generated from the actual 2026-10-01 Senior Product
Owner run). The synthetic fixtures cover branches the real pool happens not to
contain (below-level, sub-floor, no-target-seniority).

Expected verdicts are DRAFT pending the user's rule tweaks; when the rules are
finalised, only the fixtures' "expected"/"expected_reason" fields change — the
gate code does not.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from backend.services.admission import (
    REASON_BELOW_EXPERIENCE_FLOOR,
    REASON_LEVEL_ABOVE,
    REASON_LEVEL_BELOW,
    evaluate_eligibility,
    partition_by_eligibility,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "admission_regression"


def _load_fixtures() -> List[dict]:
    fixtures = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
            data["_path"] = path.name
            fixtures.append(data)
    return fixtures


def _fixture_cases():
    cases = []
    for fixture in _load_fixtures():
        for index, candidate in enumerate(fixture["candidates"]):
            cases.append(pytest.param(fixture["jd_id"], candidate, id=f"{fixture['jd_id']}[{index}:{candidate['ref'][:30]}]"))
    return cases


def test_fixture_dir_is_not_empty() -> None:
    fixtures = _load_fixtures()
    assert fixtures, "No admission regression fixtures found"
    # The real Epiq anchor must always be present.
    assert any(f["jd_id"] == "epiq_senior_product_owner" for f in fixtures)


@pytest.mark.parametrize("jd_id,candidate", _fixture_cases())
def test_gate_verdict_matches_expected_label(jd_id: str, candidate: dict) -> None:
    """Every candidate in every fixture: the gate's decision and reason must
    match the human-reviewed expected label."""
    eligible, reason = evaluate_eligibility(candidate["level_fit"], candidate["experience_floor"])
    expected_eligible = candidate["expected"] == "admit"

    assert eligible is expected_eligible, (
        f"[{jd_id}] {candidate['ref']!r} (level_fit={candidate['level_fit']}, "
        f"experience_floor={candidate['experience_floor']}): gate said "
        f"{'admit' if eligible else 'exclude'}, fixture expects {candidate['expected']}"
    )
    if not expected_eligible:
        assert reason == candidate["expected_reason"], (
            f"[{jd_id}] {candidate['ref']!r}: exclusion reason {reason!r} "
            f"!= expected {candidate['expected_reason']!r}"
        )


def test_gate_never_fires_on_unclear_or_null_level() -> None:
    """Load-bearing safety invariant: an unreliable ('unclear') or absent
    (null) level signal must never exclude a candidate, regardless of the
    experience floor being unknown. Only a hard False floor can, and only
    independently of level."""
    for level in ("unclear", None):
        for floor in (True, None):
            eligible, reason = evaluate_eligibility(level, floor)
            assert eligible is True, f"gate wrongly fired on level_fit={level}, floor={floor}"
            assert reason is None


def test_partition_preserves_order_within_each_group() -> None:
    """partition_by_eligibility keeps incoming rank order inside both the
    eligible and excluded groups — it gates, it does not re-rank."""
    # (id, level_fit, experience_floor)
    ranked = [
        ("a", "aligned", True),
        ("b", "above", True),
        ("c", "unclear", True),
        ("d", "below", True),
        ("e", "aligned", False),
        ("f", "aligned", True),
    ]
    result = partition_by_eligibility(ranked, alignment_of=lambda c: (c[1], c[2]))

    assert [c[0] for c in result.eligible] == ["a", "c", "f"]
    assert [(e.candidate[0], e.reason) for e in result.excluded] == [
        ("b", REASON_LEVEL_ABOVE),
        ("d", REASON_LEVEL_BELOW),
        ("e", REASON_BELOW_EXPERIENCE_FLOOR),
    ]


def test_epiq_anchor_demotes_the_six_above_level_candidates() -> None:
    """The headline result of the whole exercise: on the real Epiq pool, the
    gate must exclude exactly the six level_fit==above candidates (the
    Director-in-a-Senior-search shape) and admit the aligned/unclear ones —
    including the top two 'unclear' candidates, which must survive."""
    epiq = next(f for f in _load_fixtures() if f["jd_id"] == "epiq_senior_product_owner")
    result = partition_by_eligibility(
        epiq["candidates"],
        alignment_of=lambda c: (c["level_fit"], c["experience_floor"]),
    )
    excluded_refs = {e.candidate["ref"] for e in result.excluded}

    assert len(result.excluded) == 6
    assert all(e.reason == REASON_LEVEL_ABOVE for e in result.excluded)
    # The two top-scoring candidates are 'unclear' and must NOT be excluded.
    top_two = epiq["candidates"][:2]
    assert all(c["ref"] not in excluded_refs for c in top_two)
