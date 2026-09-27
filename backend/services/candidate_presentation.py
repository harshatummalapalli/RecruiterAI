"""Which reviewed candidates are shown to the recruiter, and in what batches.

Every processed candidate (up to 25 per retrieval cycle) is kept. Only a few are PRESENTED at a time; the rest are
RESERVE: reviewed, evidence intact, simply not shown yet. Reserve is never a rejection.

The evidence level is the same fixed rule the workspace already uses to group a profile (frontend models/workspace.ts
`sectionOf`): the share of the core requirements, not counting total years, that the profile shows. It is a rule about
the profile, not a score and not a rank.

    strong     at least 60% of the non-years core requirements are shown
    some       at least one is shown
    thin       none is shown
    unchecked  the core requirements could not be checked against the profile
"""

from typing import Any, Dict, List, Optional, Sequence

PRESENTED = "presented"
RESERVE = "reserve"

STRONG = "strong"
SOME = "some"
THIN = "thin"
UNCHECKED = "unchecked"

# Same threshold as the workspace's START_HERE_SHARE.
STRONG_SHARE = 0.6

INITIAL_BATCH = 5
INITIAL_MIX = {STRONG: 3, SOME: 2}
MORE_BATCH = 5

# Fill order when a batch cannot be filled from the preferred levels: nothing known against a profile ranks above a
# profile that was checked and showed nothing.
LEVEL_ORDER = [STRONG, SOME, UNCHECKED, THIN]


def evidence_level(evidence: Optional[Dict[str, Any]]) -> str:
    judgments = (evidence or {}).get("requirement_judgments")
    if not judgments:
        return UNCHECKED
    core = [j for j in judgments if j.get("tier") == "core" and (j.get("source") or "").lower() != "career dates"]
    if not core:
        return UNCHECKED
    shown = sum(1 for j in core if j.get("verdict") == "met")
    if shown == 0:
        return THIN
    return STRONG if shown / len(core) >= STRONG_SHARE else SOME


def _by_level(rows: Sequence[Dict[str, Any]], level: str) -> List[Dict[str, Any]]:
    return [row for row in rows if row["level"] == level]


def pick_batch(rows: Sequence[Dict[str, Any]], count: int, *, initial: bool = False) -> List[str]:
    """Choose candidate ids from the reserve rows. Each row: {id, index, level, guidance}. `index` is the order the
    search returned them in; `guidance` is the feedback tie-break (0.0 when there is none).

    The first batch is 3 with strong evidence and 2 with some, filled from the next available levels when short. Later
    batches are simply the strongest evidence first. Within a level: guidance, then the order the search returned."""

    def in_level_order(level_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(level_rows, key=lambda row: (-row.get("guidance", 0.0), row["index"]))

    chosen: List[Dict[str, Any]] = []
    remaining = list(rows)

    if initial:
        for level, quota in INITIAL_MIX.items():
            for row in in_level_order(_by_level(remaining, level))[:quota]:
                chosen.append(row)
        chosen_ids = {row["id"] for row in chosen}
        remaining = [row for row in remaining if row["id"] not in chosen_ids]

    for level in LEVEL_ORDER:
        if len(chosen) >= count:
            break
        for row in in_level_order(_by_level(remaining, level)):
            if len(chosen) >= count:
                break
            chosen.append(row)

    return [row["id"] for row in chosen[:count]]


def reserve_rows(record: Dict[str, Any], guidance_score) -> List[Dict[str, Any]]:
    """The candidates waiting to be shown, with what pick_batch needs. Stale ones (found under an earlier version of
    the brief) are not offered."""
    response = record.get("response") or {}
    candidates = response.get("candidates") or []
    evidence = response.get("evidence") or []
    states = record.get("candidate_states") or {}
    rows: List[Dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        candidate_id = candidate.get("candidate_id")
        entry = (record.get("presentation") or {}).get(candidate_id)
        if not candidate_id or not entry or entry.get("state") != RESERVE or entry.get("stale"):
            continue
        if states.get(candidate_id) != "review_ready":
            continue
        item_evidence = evidence[index] if index < len(evidence) else {}
        rows.append(
            {
                "id": candidate_id,
                "index": index,
                "level": evidence_level(item_evidence),
                "guidance": guidance_score(item_evidence),
            }
        )
    return rows


def present(record: Dict[str, Any], candidate_ids: Sequence[str], *, batch: int) -> None:
    presentation = record.setdefault("presentation", {})
    for candidate_id in candidate_ids:
        entry = presentation.get(candidate_id)
        if entry is not None:
            entry["state"] = PRESENTED
            entry["batch"] = batch
            entry["seen"] = True
            entry.pop("stale", None)


def next_batch_number(record: Dict[str, Any]) -> int:
    batches = [entry.get("batch", 0) for entry in (record.get("presentation") or {}).values() if entry.get("state") == PRESENTED]
    return (max(batches) + 1) if batches else 1


def counts(record: Dict[str, Any]) -> Dict[str, int]:
    presentation = record.get("presentation") or {}
    presented = sum(1 for entry in presentation.values() if entry.get("state") == PRESENTED)
    reserve = sum(1 for entry in presentation.values() if entry.get("state") == RESERVE)
    new = sum(1 for entry in presentation.values() if entry.get("state") == RESERVE and entry.get("source") in ("daily", "resume") and not entry.get("seen") and not entry.get("stale"))
    return {"presented": presented, "reserve": reserve, "new": new}
