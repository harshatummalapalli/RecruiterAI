"""OpenAI-backed capability proposer — the learned taxonomy's "propose on a
miss" step. Rare (once per new role shape, then cached), so it can use a strong
model. Parsing is pure and tested; the network call is lazy and fails safe
(returns None -> the role stays broad, never a wrong narrow guess).
"""

from __future__ import annotations

import json
from typing import List, Optional

from recruiter.agents.intake.capability_memory import LearnedCapability

_SYSTEM = (
    "You identify a role's single DEFINING specialization and the interchangeable "
    "surface terms a practitioner's profile would actually use for it. Return ONLY "
    'JSON: {"broad": bool, "label": str, "qualifier": str, "terms": [str]}. '
    "Set broad=true when the role has no single defining specialization (e.g. a plain "
    "'Backend Engineer' or 'Project Manager'). When not broad: label is a short name "
    "(e.g. 'Salesforce', 'Agentic AI'); qualifier is the identity token that marks it "
    "(e.g. 'AI'); terms are 5-9 whole-word EVIDENCE terms a profile would contain "
    "(skills/tools/techniques, never job titles). Be conservative: if unsure, broad=true."
)


def _parse_proposal(data) -> Optional[LearnedCapability]:
    if not isinstance(data, dict) or data.get("broad"):
        return None
    terms = [t.strip() for t in (data.get("terms") or []) if isinstance(t, str) and t.strip()]
    label = (data.get("label") or "").strip()
    if not terms or not label:
        return None
    qualifier = (data.get("qualifier") or "").strip() or label
    return LearnedCapability("", label, tuple(dict.fromkeys(terms)), qualifier)


def _user_prompt(identity: str, posted_title: Optional[str], requirement_texts: List[str]) -> str:
    lines = [f"Role identity: {identity}"]
    if posted_title and posted_title != identity:
        lines.append(f"Posted title: {posted_title}")
    if requirement_texts:
        lines.append("Requirements: " + "; ".join(requirement_texts))
    return "\n".join(lines) + "\n\nReturn the JSON now."


def make_openai_proposer(client=None, model: str = "gpt-4o-mini"):
    """Returns an LlmProposer: (identity, posted_title, requirement_texts) ->
    LearnedCapability | None. Client is created lazily; any failure -> None."""

    state = {"client": client}

    def propose(identity: str, posted_title: Optional[str], requirement_texts: List[str]) -> Optional[LearnedCapability]:
        try:
            if state["client"] is None:
                from openai import OpenAI
                from backend.config import get_openai_api_key
                key = get_openai_api_key()
                if not key:
                    return None
                state["client"] = OpenAI(api_key=key)
            response = state["client"].responses.create(
                model=model,
                input=[{"role": "system", "content": _SYSTEM},
                       {"role": "user", "content": _user_prompt(identity, posted_title, requirement_texts)}],
                text={"format": {"type": "json_object"}},
                temperature=0,
            )
            return _parse_proposal(json.loads(response.output_text))
        except Exception:
            return None

    return propose
