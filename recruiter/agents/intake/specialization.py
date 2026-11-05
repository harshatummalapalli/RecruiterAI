"""Detect a super-type title that needs narrowing, and ask which specialization —
then, once a specialization is pinned, which stack — when the role's OWN evidence
doesn't already answer it.

Deterministic and offline. It only asks when genuinely ambiguous (a role whose
requirements already point clearly at one kind, or already name a stack, is left
alone — no nag), and a stack is NEVER inferred from silence: "Any stack is fine"
is a first-class answer. The knowledge tables are seeded with the families that
bite most and grow over time (ROLE_UNDERSTANDING_PLAN.md Thread B).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from recruiter.agents.intake.capability_memory import normalise_key
from recruiter.agents.intake.model import Question


def _matches(term: str, hay: str) -> bool:
    """Match a signal term at a WORD START (prefix ok), not as a bare substring:
    'api' matches 'APIs', but 'ui' must not match 'built'. Live validation showed
    naive `in` false-pinned Frontend via 'ui' ⊂ 'built' (2026-11-05)."""
    return re.search(r"(?<![a-z0-9])" + re.escape(term), hay) is not None

# label -> signal terms (lowercase, substring-matched against identity+requirements).
_Axis = Tuple[Tuple[str, Tuple[str, ...]], ...]

_SOFTWARE: _Axis = (
    ("Backend", ("backend", "server-side", "server side", "api", "microservice", "distributed", "database")),
    ("Frontend", ("frontend", "front-end", "react", "ui", "css", "browser")),
    ("Full-stack", ("full stack", "full-stack", "end-to-end", "frontend and backend")),
    ("Mobile", ("ios", "android", "mobile", "swift", "kotlin", "react native")),
    ("Data", ("data pipeline", "etl", "spark", "warehouse", "data engineering")),
    ("ML", ("machine learning", "ml model", "training", "inference", "model serving")),
    ("DevOps / SRE", ("devops", "sre", "kubernetes", "ci/cd", "infrastructure", "reliability")),
)
_AI: _Axis = (
    ("Applied / GenAI", ("prompt", "rag", "retrieval", "llm", "genai", "agent")),
    ("ML / modelling", ("train", "fine-tune", "model architecture", "pytorch", "research", "deep learning")),
    ("ML platform / MLOps", ("serving", "mlops", "feature store", "pipeline", "sagemaker", "inference infra")),
    ("Data science", ("statistics", "experiment", "a/b", "analysis", "notebook")),
)
_ANALYST: _Axis = (
    ("Financial / FP&A", ("fp&a", "forecast", "budget", "variance", "financial model", "accounting")),
    ("Data / BI", ("sql", "dashboard", "bi", "tableau", "power bi", "looker")),
    ("Risk", ("risk", "credit risk", "compliance", "fraud")),
    ("Operations", ("operations", "process", "workflow", "ops")),
)

# super-type key (seniority-stripped identity) -> its specializations.
_SPECIALIZATIONS: Dict[str, _Axis] = {
    "software engineer": _SOFTWARE, "engineer": _SOFTWARE,
    "developer": _SOFTWARE, "software developer": _SOFTWARE, "programmer": _SOFTWARE,
    "ai engineer": _AI,
    "analyst": _ANALYST,
}

# specialization label -> its stack axis (option label -> surface terms). A chosen
# option becomes a precise any-of keyword filter; the terms double as the detector
# for "a stack is already named". Bare "Go" is not a safe substring, so it is
# offered as an option but detected only via "golang".
_STACKS: Dict[str, _Axis] = {
    "Backend": (
        ("Java", ("java", "spring", "jvm")),
        (".NET / C#", (".net", "c#", "asp.net", "dotnet")),
        ("Python", ("python", "django", "flask", "fastapi")),
        ("Node.js", ("node.js", "nodejs", "node ", "express", "nestjs")),
        ("Go", ("golang",)),
        ("Ruby", ("ruby", "rails")),
        ("PHP", ("php", "laravel", "symfony")),
    ),
    "Frontend": (
        ("React", ("react",)),
        ("Angular", ("angular",)),
        ("Vue", ("vue",)),
    ),
    "Mobile": (
        ("iOS / Swift", ("ios", "swift")),
        ("Android / Kotlin", ("android", "kotlin")),
        ("Cross-platform", ("react native", "flutter")),
    ),
}

_ANY_STACK = "Any stack is fine"


def _hay(identity: str, requirement_texts: Sequence[str]) -> str:
    return " ".join([identity, *requirement_texts]).lower()


def _leaders(axis: _Axis, hay: str) -> List[str]:
    scored = [(label, sum(1 for term in terms if _matches(term, hay))) for label, terms in axis]
    top = max(score for _, score in scored)
    return [label for label, score in scored if score == top and score > 0]


def disambiguate(identity: str, requirement_texts: Sequence[str]) -> Optional[Question]:
    """A specialization question when the title is a broad super-type AND the role's
    own evidence doesn't single out one kind; otherwise None."""
    axis = _SPECIALIZATIONS.get(normalise_key(identity))
    if not axis:
        return None
    if len(_leaders(axis, _hay(identity, requirement_texts))) == 1:
        return None  # evidence already pins one specialization — no need to ask
    return Question(
        id="specialization", kind="choice", routing="query/filter",
        prompt=f"“{identity}” is broad — which kind is this role?",
        options=tuple(label for label, _ in axis),
    )


# A specialization named IN the identity itself (e.g. "Backend Engineer", or the
# reader's rewritten "Backend Software Engineer") — so the stack axis is reachable
# even when the title isn't a bare super-type. Label -> identity keywords.
_IDENTITY_SPEC: _Axis = (
    ("Backend", ("backend", "back-end", "back end", "server-side")),
    ("Frontend", ("frontend", "front-end", "front end", "ui engineer")),
    ("Full-stack", ("full stack", "full-stack", "fullstack")),
    ("Mobile", ("mobile", "ios", "android")),
    ("Data", ("data engineer",)),
    ("ML", ("machine learning engineer", "ml engineer")),
    ("DevOps / SRE", ("devops", "sre", "site reliability")),
)


def _specialization_from_identity(identity: str) -> Optional[str]:
    low = (identity or "").lower()
    for label, keywords in _IDENTITY_SPEC:
        if any(_matches(kw, low) for kw in keywords):
            return label
    return None


def pinned_specialization(identity: str, requirement_texts: Sequence[str]) -> Optional[str]:
    """The single specialization the evidence points to, or None when broad/ambiguous."""
    axis = _SPECIALIZATIONS.get(normalise_key(identity))
    if not axis:
        return None
    leaders = _leaders(axis, _hay(identity, requirement_texts))
    return leaders[0] if len(leaders) == 1 else None


def resolved_specialization(identity: str, requirement_texts: Sequence[str]) -> Optional[str]:
    """The role's specialization, from the identity itself first (a title like
    "Backend Engineer" already names it), else the super-type + evidence route."""
    return _specialization_from_identity(identity) or pinned_specialization(identity, requirement_texts)


def stack_question(identity: str, requirement_texts: Sequence[str]) -> Optional[Question]:
    """Once a specialization is pinned but no stack is named, ask which — with
    "Any stack is fine" as a real answer. None when no stack axis applies or one is
    already named."""
    label = resolved_specialization(identity, requirement_texts)
    if not label:
        return None
    stacks = _STACKS.get(label)
    if not stacks:
        return None
    hay = _hay(identity, requirement_texts)
    if any(_matches(term, hay) for _, terms in stacks for term in terms):
        return None  # a stack is already named — it is picked up directly
    return Question(
        id="stack", kind="choice", routing="filter", payload=label,
        prompt=f"No specific {label} stack is named — is a particular one required?",
        options=tuple(label for label, _ in stacks) + (_ANY_STACK,),
    )


def is_any_stack(answer: str) -> bool:
    return str(answer).strip().lower() == _ANY_STACK.lower()


def stack_terms(label: str) -> Tuple[str, ...]:
    """The surface spellings for a chosen stack option (the any-of filter terms)."""
    for stacks in _STACKS.values():
        for option, terms in stacks:
            if option == label:
                return terms
    return ()
