"""Provider-agnostic intake reader: runs the keeper's two-task intake (Task A
understanding + Task B decision) through recruiter.llm.complete_json, so the
reader works on OpenAI OR Claude by model name. Reuses the keeper's prompts and
its PURE parsing/backstop functions (no re-implementation of that logic); only
the LLM call is swapped. This is the migrated reader — it supersedes the
OpenAI-only keeper_reader once validated.
"""

from __future__ import annotations

import json
from typing import Optional

from recruiter.agents.intake.model import Understanding
from recruiter.agents.intake.reader import _to_understanding


def _task_a_user_prompt(raw_input: str, posted_title: Optional[str]) -> str:
    title_line = ""
    if posted_title and posted_title.strip():
        title_line = (
            f'\n\nThe recruiter states the posted title is exactly: "{posted_title.strip()}". '
            "Use it verbatim as posted_title."
        )
    return f"Raw hiring input:\n{raw_input}{title_line}\n\nReturn the JSON now."


def make_native_reader(model: str):
    def reader(notes: str, posted_title: Optional[str] = None) -> Understanding:
        from backend.services.intake_reasoning import (
            PROMPTS_DIR,
            apply_intake_backstops,
            apply_posted_title,
            parse_intake_decision,
            parse_role_understanding,
            reconcile_role_defining_capability,
            role_understanding_to_dict,
        )
        from backend.services.requirement_provenance import apply_field_provenance, attach_requirement_evidence
        from backend.models.intake import IntakeResult
        from recruiter.llm import complete_json

        # Task A — role understanding.
        system_a = (PROMPTS_DIR / "intake_task_a_understanding.txt").read_text(encoding="utf-8")
        raw_a = complete_json(system_a, _task_a_user_prompt(notes, posted_title), model, max_tokens=4096)
        role_understanding = parse_role_understanding(raw_a)
        apply_posted_title(role_understanding, notes, posted_title)
        apply_field_provenance(role_understanding, notes)

        # Task B — the ASK/TELL decision + tiered intent.
        template = (PROMPTS_DIR / "intake_task_b_decision.txt").read_text(encoding="utf-8")
        user_b = template.replace(
            "{role_understanding_json}", json.dumps(role_understanding_to_dict(role_understanding))
        ).replace("{raw_input}", notes)
        system_b = "Follow the instructions in the user message exactly and return only the JSON they specify."
        raw_b = complete_json(system_b, user_b, model, max_tokens=4096)
        decision = parse_intake_decision(raw_b)
        attach_requirement_evidence(decision, notes)

        # Deterministic backstops (same as the keeper).
        reconcile_role_defining_capability(role_understanding, decision)
        decision, contradictions = apply_intake_backstops(
            notes, bool(role_understanding.explicit_constraints.locations), decision
        )
        status = "needs_clarification" if any(i.decision == "ask" for i in decision.issues) else "ready"
        result = IntakeResult(
            raw_input=notes, role_understanding=role_understanding,
            decision=decision, contradictions=contradictions, status=status,
        )
        return _to_understanding(notes, posted_title, result)

    return reader
