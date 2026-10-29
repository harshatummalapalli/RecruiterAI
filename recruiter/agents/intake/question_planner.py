"""The adaptive question planner (refinement 2).

Given the role read + the proposed capability, produce the MINIMAL set of
optional refinement questions that are (a) relevant to this role and (b)
actionable on CrustData. Each question is labelled with how its answer is used
(filter / judge / ranking / confirm) so the recruiter sees why it's asked, and
nothing unenforceable is ever presented as a filter.

Years is the one REQUIRED question and is handled in assemble.py (it blocks);
everything here is optional and surfaced on the brief. Proof-of-work phrasing
(#3) and candidate archetype (#4) are reader/Judge concerns, not recruiter
questions, so they are intentionally not asked here.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from recruiter.agents.intake.model import Question, Understanding
from recruiter.role_model import CapabilityGroup, classify_role_level

FILTER, QUERY, JUDGE, RANKING, CONFIRM = "filter", "query", "judge", "ranking", "confirm"

_DOMAIN_HINTS = (
    "fintech", "payments", "banking", "insurance", "healthcare", "health", "ecommerce",
    "e-commerce", "gaming", "edtech", "logistics", "telecom", "retail", "cybersecurity",
    "defense", "aerospace", "automotive", "manufacturing", "pharma", "biotech",
)

_LOOKALIKE_PRONE = ("architect", "manager", "director+")


def _detect_domain(text: str) -> Optional[str]:
    low = text.lower()
    for hint in _DOMAIN_HINTS:
        if hint in low:
            return hint
    return None


def plan_refinements(
    understanding: Understanding,
    capability_groups: Tuple[CapabilityGroup, ...],
) -> List[Question]:
    identity = understanding.identity
    role_level = classify_role_level(identity, understanding.posted_title)
    core_texts = tuple(r.text for r in understanding.requirements if r.tier == "core")
    text_blob = " ".join([identity] + [r.text for r in understanding.requirements])

    questions: List[Question] = []

    # (capability) confirm the learned/proposed role-defining capability — this
    # is also the recruiter-confirm step of the learning loop.
    for group in capability_groups:
        shown = ", ".join(group.terms[:6]) + ("…" if len(group.terms) > 6 else "")
        questions.append(Question(
            id="capability", kind="capability_confirm", routing=FILTER,
            prompt=f"This reads as a {group.label} role — require evidence of it (any of: {shown})? Remove to widen.",
            options=("keep", "remove"),
        ))

    # (1) dealbreakers — which cores are truly non-negotiable.
    if len(core_texts) >= 2:
        questions.append(Question(
            id="dealbreakers", kind="multi_select", routing=f"{FILTER}/{JUDGE}",
            prompt="Which of these are true dealbreakers (non-negotiable)?",
            options=core_texts,
        ))

    # (6) priority among the cores — breaks ranking ties on merit.
    if len(core_texts) >= 2:
        questions.append(Question(
            id="priority", kind="rank", routing=RANKING,
            prompt="Rank these must-haves by importance (the top one matters most for ranking).",
            options=core_texts,
        ))

    # (5) domain — only when the notes actually carry one (CrustData can filter industry).
    domain = _detect_domain(text_blob)
    if domain:
        questions.append(Question(
            id="domain", kind="choice", routing=FILTER,
            prompt=f"Is {domain} domain experience required, preferred, or irrelevant?",
            options=("required", "preferred", "irrelevant"),
        ))

    # (2) disqualifiers — offered for look-alike-prone roles (specialised or senior).
    if capability_groups or role_level in _LOOKALIKE_PRONE:
        questions.append(Question(
            id="disqualifiers", kind="free_text", routing=JUDGE,
            prompt="Anything that should rule a candidate out? (e.g. agency-only, research-only, no production experience)",
        ))

    # (7) confirm the interpretation — only where a misread is costly.
    if role_level in _LOOKALIKE_PRONE:
        questions.append(Question(
            id="confirm_level", kind="confirm", routing=CONFIRM,
            prompt=f"I read this as a(n) {role_level} role ({identity}). Is that right?",
            options=("yes", "no"),
        ))

    return questions
