"""Agent 1 — Intake. Hiring notes + recruiter boundary -> RoleModel.

Orchestrates only: read the notes (LLM, injectable), then assemble the spine
(pure). The read and the assemble are separate so the clarification loop can
answer without re-reading the notes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from recruiter.agents.intake.assemble import assemble_role_model
from recruiter.agents.intake.model import IntakeOutcome, Understanding
from recruiter.agents.intake.reader import keeper_reader

Reader = Callable[[str, Optional[str]], Understanding]


class IntakeAgent:
    def __init__(self, reader: Reader = keeper_reader) -> None:
        self._reader = reader

    def read(self, notes: str, posted_title: Optional[str] = None) -> Understanding:
        return self._reader(notes, posted_title)

    def assemble(
        self,
        understanding: Understanding,
        boundary: Dict[str, Any],
        answers: Optional[Dict[str, Any]] = None,
    ) -> IntakeOutcome:
        return assemble_role_model(understanding, boundary, answers)

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
