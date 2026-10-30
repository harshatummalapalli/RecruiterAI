"""Agent 1 — Intake. Hiring notes + recruiter boundary -> RoleModel.

Orchestrates (impure) the read, the capability proposal (per-org memory + LLM),
and the pure assembly. Read and assemble are separate so the clarification loop
answers without re-reading the notes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from recruiter.agents.intake.assemble import assemble_role_model, normalize_identity
from recruiter.agents.intake.capability_memory import FileCapabilityMemory
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import IntakeOutcome, Understanding
from recruiter.agents.intake.question_planner import plan_refinements
from recruiter.agents.intake.reader import keeper_reader

Reader = Callable[[str, Optional[str]], Understanding]

_DEFAULT_MEMORY_ROOT = Path("output/capability_memory")


class IntakeAgent:
    def __init__(
        self,
        reader: Reader = keeper_reader,
        capability_proposer: Optional[CapabilityProposer] = None,
        org: str = "default",
    ) -> None:
        self._reader = reader
        self._org = org
        # Default proposer: per-org file memory, no LLM yet -> stays broad until
        # a proposer learns a capability (honest; no hand-seeded families).
        self._capabilities = capability_proposer or CapabilityProposer(FileCapabilityMemory(_DEFAULT_MEMORY_ROOT))

    def read(self, notes: str, posted_title: Optional[str] = None) -> Understanding:
        return self._reader(notes, posted_title)

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
    ) -> IntakeOutcome:
        understanding = self.read(notes, posted_title or boundary.get("posted_title"))
        return self.assemble(understanding, boundary, answers)
