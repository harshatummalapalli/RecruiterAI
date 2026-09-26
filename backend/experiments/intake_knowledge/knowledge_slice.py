"""Selects a SMALL slice of the Knowledge Library as advisory context for the intake decision (Task B).

Knowledge informs, the LLM reasons, code validates. This module only chooses which few lines of recruiter knowledge
might be relevant to THIS role and renders them as text. It never decides anything, never blocks anything, and
nothing it returns is a rule. Whether it is used at all is controlled by the caller (see
backend/experiments/intake_knowledge for the measurement that decides that).

Selection is deterministic: the same role understanding always yields the same slice.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
MAX_SLICE_CHARS = 6000

# Role-cluster files and the hiring-pattern family ids that belong with each.
_CLUSTERS = {
    "ai-engineering-roles": ["ai-engineering", "applied-ai-engineering", "ml-engineering"],
    "backend-roles": ["backend-engineering", "backend"],
    "platform-roles": ["platform-engineering", "devops", "sre", "infrastructure"],
    "data-roles": ["data-engineering", "data-science", "analytics-engineering"],
}

FRAMING = (
    "Reference knowledge (advisory context from recruiting practice, NOT rules). Use it only to notice a genuine "
    "issue that already meets the ASK/TELL criteria above. Never create a question because a pattern exists here, "
    "and ignore anything that does not clearly apply to this role."
)


@dataclass
class KnowledgeSlice:
    text: str = ""
    sources: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.text)


@lru_cache(maxsize=None)
def _load(name: str) -> Dict[str, Any]:
    path = KNOWLEDGE_DIR / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _haystack(understanding: Dict[str, Any]) -> str:
    parts: List[str] = [
        (understanding.get("posted_title") or ""),
        ((understanding.get("primary_candidate_identity") or {}).get("value") or ""),
        ((understanding.get("candidate_archetype") or {}).get("value") or ""),
    ]
    for key in ("core_capabilities", "supporting_capabilities", "differentiators"):
        parts.extend((item or {}).get("value") or "" for item in understanding.get(key) or [])
    for group in understanding.get("technologies_mentioned") or []:
        parts.extend(group.get("items") or [])
    parts.extend(understanding.get("domain") or [])
    return " ".join(parts).lower()


def _mentions(haystack: str, term: str) -> bool:
    term = (term or "").strip().lower()
    return bool(term) and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack) is not None


def _cluster_scores(haystack: str) -> Dict[str, int]:
    scores: Dict[str, int] = {}
    for name in _CLUSTERS:
        data = _load(name)
        score = 0
        for role in data.get("roles") or []:
            if _mentions(haystack, role.get("title", "")):
                score += 3
            score += sum(1 for tech in role.get("typical_stack") or [] if _mentions(haystack, str(tech)))
        scores[name] = score
    return scores


def _render_cluster(name: str) -> str:
    data = _load(name)
    lines = [f"Role cluster: {data.get('cluster', name)}"]
    for role in data.get("roles") or []:
        focus = " ".join(str(role.get("distinguishing_focus", "")).split())
        confused = ", ".join(role.get("commonly_confused_with") or [])
        lines.append(f"- {role.get('title')}: {focus}" + (f" (often confused with: {confused})" if confused else ""))
    return "\n".join(lines)


def _render_patterns(family_ids: Iterable[str], seniority_words: bool) -> str:
    data = _load("hiring-patterns")
    lines: List[str] = []
    wanted = set(family_ids)
    for entry in data.get("by_role_family") or []:
        if entry.get("role_family_id") in wanted:
            lines.extend(f"- {guidance}" for guidance in entry.get("guidance") or [])
    if seniority_words:
        for entry in data.get("by_seniority") or []:
            lines.extend(f"- {guidance}" for guidance in entry.get("guidance") or [])
    return "Hiring patterns:\n" + "\n".join(lines) if lines else ""


def _render_mistakes() -> str:
    data = _load("common-hiring-mistakes")
    lines = ["Recurring JD/search pitfalls (to notice, not to enforce):"]
    for item in data.get("mistakes") or []:
        summary = " ".join(str(item.get("summary", "")).split())
        lines.append(f"- {summary}")
    return "\n".join(lines)


def _render_relationships(haystack: str, limit: int = 8) -> str:
    data = _load("technology-relationships")
    lines: List[str] = []
    for item in data.get("technology_relationships") or []:
        if _mentions(haystack, item.get("from", "")) or _mentions(haystack, item.get("to", "")):
            note = " ".join(str(item.get("notes", "")).split())
            lines.append(f"- {item.get('from')} {item.get('relationship')} {item.get('to')}: {note}")
        if len(lines) >= limit:
            break
    return "Technology relationships:\n" + "\n".join(lines) if lines else ""


def select_knowledge_slice(understanding: Dict[str, Any]) -> KnowledgeSlice:
    """`understanding` is the role-understanding dict (see role_understanding_to_dict)."""
    haystack = _haystack(understanding)
    scores = _cluster_scores(haystack)
    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    chosen = [name for name, score in ranked[:2] if score >= 2]

    sections: List[tuple[str, str]] = []
    family_ids: List[str] = []
    for name in chosen:
        sections.append((name, _render_cluster(name)))
        family_ids.extend(_CLUSTERS[name])
    seniority = bool(re.search(r"\b(staff|principal|senior|lead|architect)\b", haystack))
    patterns = _render_patterns(family_ids, seniority_words=seniority)
    if patterns:
        sections.append(("hiring-patterns", patterns))
    relationships = _render_relationships(haystack)
    if relationships:
        sections.append(("technology-relationships", relationships))
    sections.append(("common-hiring-mistakes", _render_mistakes()))

    text = FRAMING
    used: List[str] = []
    for source, body in sections:
        if len(text) + len(body) + 2 > MAX_SLICE_CHARS:
            continue
        text += "\n\n" + body
        used.append(source)
    return KnowledgeSlice(text=text, sources=used)
