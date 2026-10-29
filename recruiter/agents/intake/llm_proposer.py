"""OpenAI-backed capability proposer — the learned taxonomy's "propose on a
miss" step. Rare (once per new role shape, then cached), so it can use a strong
model. Parsing is pure and tested; the network call is lazy and fails safe
(returns None -> the role stays broad, never a wrong narrow guess).
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from recruiter.agents.intake.capability_memory import LearnedCapability

_SYSTEM = (
    "You name a role's ONE defining specialization and the interchangeable surface terms "
    "a matching candidate's profile would contain for THAT capability.\n\n"
    'Return ONLY JSON: {"broad": bool, "label": str, "qualifier": str, "terms": [str]}.\n'
    "- broad=true when the role has no single defining specialization (a plain 'Backend "
    "Engineer', 'Project Manager', 'Data Analyst'). Then label/qualifier/terms are ignored.\n"
    "- label: a short CAPABILITY name, never a job title (e.g. 'Agentic AI', 'Salesforce', "
    "'Site Reliability'); never 'AI Architect'.\n"
    "- terms: 5-9 interchangeable EVIDENCE words/acronyms for that ONE capability as they "
    "appear on profiles.\n"
    "- terms must NOT include: programming languages (Java, Python...), generic engineering "
    "words (software engineering, development, architecture, systems), the job title, or "
    "other requirements. Those are context, not the capability's synonyms.\n"
    "- Be conservative: if unsure, broad=true.\n\n"
    "Example — identity 'AI Solutions Architect', requirements 'Java, Python, RAG, Agentic systems':\n"
    '{"broad": false, "label": "Agentic AI", "qualifier": "AI", '
    '"terms": ["AI","ML","LLM","RAG","GenAI","agentic","agents","LangChain"]}\n'
    "(Java and Python are requirements, NOT capability terms, so they are excluded.)"
)

# Deterministic backstop ("code validates the LLM"): tokens that are never, on
# their own, a role-defining capability's synonym. A term is dropped only when
# EVERY one of its tokens is generic — so "AI" and "agentic systems" survive,
# but "Java Development", "Python" and "Software Engineering" do not.
_GENERIC_TOKENS = {
    "java", "python", "c", "c++", "c#", ".net", "net", "javascript", "typescript", "go",
    "golang", "ruby", "scala", "rust", "kotlin", "php", "sql", "software", "engineering",
    "development", "programming", "coding", "architecture", "systems", "system",
    "backend", "frontend", "stack", "full", "design",
}


def _is_generic(term: str) -> bool:
    tokens = re.findall(r"[a-z0-9+#.]+", term.lower())
    return bool(tokens) and all(tok in _GENERIC_TOKENS for tok in tokens)


def _sanitize_terms(terms: List[str], identity: str, label: str) -> List[str]:
    # Drop the role title itself (a title is not a capability synonym), but NOT
    # the label — the capability's own name (e.g. "Salesforce") is a valid term.
    drop_exact = {(identity or "").strip().lower()}
    out: List[str] = []
    for t in terms:
        clean = t.strip()
        if clean and clean.lower() not in drop_exact and not _is_generic(clean):
            out.append(clean)
    return out


def _parse_proposal(data, identity: str = "") -> Optional[LearnedCapability]:
    if not isinstance(data, dict) or data.get("broad"):
        return None
    raw_terms = [t for t in (data.get("terms") or []) if isinstance(t, str) and t.strip()]
    label = (data.get("label") or "").strip()
    terms = _sanitize_terms(raw_terms, identity, label)
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


def make_openai_proposer(client=None, model: str = "gpt-4o"):
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
            return _parse_proposal(json.loads(response.output_text), identity)
        except Exception:
            return None

    return propose
