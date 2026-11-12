"""Agent 1 — Intake. Hiring notes + recruiter boundary -> RoleModel.

Orchestrates (impure) the read, the capability proposal (per-org memory + LLM),
and the pure assembly. Read and assemble are separate so the clarification loop
answers without re-reading the notes.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from recruiter.agents.intake.assemble import assemble_role_model, normalize_identity
from recruiter.agents.intake.capability_memory import FileCapabilityMemory
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import IntakeOutcome, Understanding
from recruiter.agents.intake.question_planner import plan_refinements
from recruiter.agents.intake.reader import keeper_reader
from recruiter.agents.intake.reconcile import (
    Matcher,
    Reconciliation,
    experience_flag,
    reconcile,
)
from recruiter.agents.intake.reconcile_semantic import make_semantic_matcher

Reader = Callable[[str, Optional[str]], Understanding]
MatcherFactory = Callable[[Understanding, Understanding], Matcher]

_DEFAULT_MEMORY_ROOT = Path("output/capability_memory")


class IntakeAgent:
    def __init__(
        self,
        reader: Reader = keeper_reader,
        capability_proposer: Optional[CapabilityProposer] = None,
        org: str = "default",
        matcher_factory: MatcherFactory = make_semantic_matcher,
    ) -> None:
        self._reader = reader
        self._org = org
        # How the JD and HM reads are paired during reconciliation. Default is the
        # semantic matcher (fail-open to deterministic); tests inject a token one.
        self._matcher_factory = matcher_factory
        # Default proposer: per-org file memory, no LLM yet -> stays broad until
        # a proposer learns a capability (honest; no hand-seeded families).
        self._capabilities = capability_proposer or CapabilityProposer(FileCapabilityMemory(_DEFAULT_MEMORY_ROOT))

    def read(self, notes: str, posted_title: Optional[str] = None) -> Understanding:
        return self._reader(notes, posted_title)

    def _read_if(self, notes: Optional[str], posted_title: Optional[str]) -> Optional[Understanding]:
        return self.read(notes, posted_title) if notes and notes.strip() else None

    def read_dual(
        self,
        jd_notes: Optional[str] = None,
        hm_notes: Optional[str] = None,
        *,
        posted_title: Optional[str] = None,
        boundary_min_years: Optional[int] = None,
    ) -> "tuple[Understanding, Optional[Reconciliation]]":
        """Read the published JD and the HM/client brief independently and
        reconcile them (feature A). Returns the proposed `Understanding` the rest
        of intake consumes, plus the `Reconciliation` diff for the recruiter's
        inline validation — or None when there is only one source, in which case
        the single read is returned UNCHANGED (A2: byte-identical to today).

        `boundary_min_years` is the recruiter's hard experience filter; when given
        it attaches the soft years sanity-catch (HM prose vs the filter)."""
        jd = self._read_if(jd_notes, posted_title)
        hm = self._read_if(hm_notes, posted_title)
        if jd is not None and hm is not None:
            rec = reconcile(jd, hm, matcher=self._matcher_factory(jd, hm))
            flag = experience_flag(hm, boundary_min_years)
            if flag is not None:
                rec = replace(rec, experience=flag)
            return rec.merged, rec
        understanding = jd if jd is not None else hm
        if understanding is None:
            raise ValueError("read_dual needs at least one of jd_notes or hm_notes")
        return understanding, None

    def assemble(
        self,
        understanding: Understanding,
        boundary: Dict[str, Any],
        answers: Optional[Dict[str, Any]] = None,
    ) -> IntakeOutcome:
        # Key the capability memory on the SAME normalized identity used
        # downstream, so a generic base title ("Operations Analyst") can't let
        # one role's learned capability (eDiscovery) contaminate another's.
        identity = normalize_identity(
            understanding.identity,
            understanding.posted_title,
            tuple(r.text for r in understanding.requirements),
        )
        groups = self._capabilities.propose(
            self._org,
            identity,
            understanding.posted_title,
            [r.text for r in understanding.requirements],
        )
        outcome = assemble_role_model(understanding, boundary, answers, capability_groups=groups)
        if not outcome.ready:
            return outcome  # a required clarification (missing years) blocks first
        return IntakeOutcome(
            model=outcome.model,
            refinements=tuple(plan_refinements(understanding, groups)),
        )

    def run(
        self,
        notes: str,
        boundary: Dict[str, Any],
        *,
        posted_title: Optional[str] = None,
        answers: Optional[Dict[str, Any]] = None,
        hm_notes: Optional[str] = None,
    ) -> IntakeOutcome:
        title = posted_title or boundary.get("posted_title")
        if hm_notes and hm_notes.strip():
            # Dual-source: reconcile JD + HM brief, then assemble the merged read.
            understanding, _ = self.read_dual(notes, hm_notes, posted_title=title)
        else:
            understanding = self.read(notes, title)   # single source -> unchanged (A2)
        return self.assemble(understanding, boundary, answers)
