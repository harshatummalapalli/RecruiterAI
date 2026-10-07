"""The path-merge DATA CONTRACT (offline; defines and tests the shape only: nothing here calls a provider or merges live results).

    Path A results ─┐
                    ├─ candidate identity deduplication ─▶ ONE record per candidate, with every contributing path id
    Path B results ─┘

Rules:
  * identity is the existing deduplication key (candidate id, else profile URL, else email, else normalized name+company): `CandidateMerger`'s;
  * a candidate found by several paths keeps ALL contributing path ids, and each path's own payload untouched (no field is overwritten, no score is merged);
  * NO path is ranked above another, NO path score is assigned, and the output order carries no meaning (it is sorted by identity, so it does not
    depend on the order the paths were given);
  * a candidate with no identity key cannot be deduplicated: it is kept, per path, flagged `identity_resolved = False`, never silently merged or dropped;
  * the evidence obligations of a merged candidate are the obligations of EACH contributing path's own context, kept apart (`obligations_by_path`):
    a candidate matched through Path A is checked against Path A's requirements, one matched through B against B's, one matched through both against both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from backend.models.candidate import Candidate
from backend.services.candidate_merger import CandidateMerger
from backend.services.downstream_context import ContextEntry, DownstreamContext

Identity = Tuple[Optional[str], Optional[str], Optional[str]]


def candidate_identity(candidate: Candidate) -> Optional[Identity]:
    """The same identity the pipeline already deduplicates on (not a new rule)."""
    return CandidateMerger()._deduplication_key(candidate)


@dataclass(frozen=True)
class MergedCandidateEvidence:
    identity: Optional[Identity]
    identity_resolved: bool
    contributing_path_ids: Tuple[str, ...]                    # every path that returned this candidate, in the plan's path order
    per_path: Mapping[str, Candidate]                         # each path's own, unmodified payload
    obligations_by_path: Mapping[str, Tuple[ContextEntry, ...]] = field(default_factory=dict)

    def obligations(self, path_id: str) -> Tuple[ContextEntry, ...]:
        return self.obligations_by_path.get(path_id, ())


def merge_path_results(results: Mapping[str, Sequence[Candidate]], path_order: Optional[Sequence[str]] = None,
                       contexts: Optional[Sequence[DownstreamContext]] = None) -> List[MergedCandidateEvidence]:
    """Deduplicate across paths by identity, keeping every contributing path id. Deterministic and order-independent. No ranking, no scoring."""
    order = list(path_order) if path_order is not None else sorted(results)
    by_path_ctx = {c.path_id: c for c in contexts or []}
    merged: Dict[Identity, Dict[str, Candidate]] = {}
    unresolved: List[Tuple[str, int, Candidate]] = []
    for path_id in order:
        for i, cand in enumerate(results.get(path_id, ())):
            key = candidate_identity(cand)
            if key is None:
                unresolved.append((path_id, i, cand))
            else:
                merged.setdefault(key, {}).setdefault(path_id, cand)      # the first payload from a path stays; a path's duplicate does not overwrite
    out: List[MergedCandidateEvidence] = []

    def obligations(paths: Sequence[str]) -> Dict[str, Tuple[ContextEntry, ...]]:
        return {pid: tuple(by_path_ctx[pid].entries) for pid in paths if pid in by_path_ctx}

    for key in sorted(merged, key=lambda k: tuple("" if x is None else str(x) for x in k)):
        paths = tuple(p for p in order if p in merged[key])
        out.append(MergedCandidateEvidence(key, True, paths, dict(merged[key]), obligations(paths)))
    for path_id, i, cand in sorted(unresolved, key=lambda t: (t[0], t[1])):
        out.append(MergedCandidateEvidence(None, False, (path_id,), {path_id: cand}, obligations([path_id])))
    return out
