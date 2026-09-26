"""Which requirements does the raw input actually state?

"Stated in JD" is a claim, so code decides it, not the model (the model's own evidence quotes were mostly
paraphrases; see docs/experiments/intake-knowledge-spike.md, EXP-002b). A requirement counts as stated when
nearly all of its meaningful words appear together in ONE sentence or line of the input. Anything else is inferred,
which is exactly what "Inferred" should mean.

Deterministic, no model call, no role-specific rules.
"""

import re
from typing import Dict, Iterable, List, Optional

from backend.models.intake import IntakeDecision, RoleUnderstanding

STATED_SHARE = 0.75  # share of a requirement's meaningful words that must appear in a single sentence
MAX_EVIDENCE_CHARS = 220

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#./-]*")
# Words that say how strongly something is wanted, not what is wanted.
_FILLER = {
    "a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "with", "using", "such", "as", "at", "by", "is", "are",
    "be", "that", "this", "any", "other", "similar", "comparable", "including", "etc", "strong", "solid", "good", "deep",
    "proven", "hands-on", "experience", "experienced", "proficiency", "proficient", "familiarity", "familiar",
    "knowledge", "understanding", "ability", "skills", "skill", "working", "work", "professional", "relevant", "years",
    "year", "yrs", "plus", "required", "preferred", "must", "have", "you", "will", "our", "your", "we", "using",
}


def _tokens(text: str) -> List[str]:
    """Lower-case words with sentence punctuation removed. "5+" becomes "5" (a count), while "C++" stays "c++"."""
    tokens: List[str] = []
    for token in _TOKEN.findall((text or "").lower()):
        token = token.rstrip(".-/")
        if token.endswith("+") and token[:-1].isdigit():
            token = token[:-1]
        if token:
            tokens.append(token)
    return tokens


def _meaningful(text: str) -> List[str]:
    return [token for token in _tokens(text) if token not in _FILLER]


def _sentences(raw_input: str) -> List[str]:
    pieces: List[str] = []
    for line in re.split(r"[\r\n]+", raw_input or ""):
        for part in re.split(r"(?<=[.;!?])\s+", line):
            part = part.strip(" \t-*•·")
            if part:
                pieces.append(part)
    return pieces


def _present(word: str, sentence_tokens: Iterable[str]) -> bool:
    tokens = set(sentence_tokens)
    if word in tokens:
        return True
    # A light stem so "APIs"/"API", "services"/"service" and "building"/"build" still match.
    stem = word[:-1] if word.endswith("s") and len(word) > 3 else word
    return any(token == stem or (len(stem) >= 4 and token.startswith(stem)) for token in tokens)


def stated_evidence(requirement: str, sentences: List[str], min_share: float = STATED_SHARE) -> Optional[str]:
    """The sentence of the input that states this requirement, or None if it is inferred."""
    words = _meaningful(requirement)
    if not words:
        return None
    best: Optional[str] = None
    best_share = 0.0
    for sentence in sentences:
        tokens = _tokens(sentence)
        share = sum(1 for word in words if _present(word, tokens)) / len(words)
        if share > best_share:
            best, best_share = sentence, share
    if best is not None and best_share >= min_share:
        return best if len(best) <= MAX_EVIDENCE_CHARS else best[: MAX_EVIDENCE_CHARS - 1].rstrip() + "…"
    return None


def apply_field_provenance(understanding: RoleUnderstanding, raw_input: str) -> None:
    """Code decides the provenance of the reading fields; the model's own `source` flag is never trusted.

    A field is "explicit" (Stated in JD) only when its value is found in one sentence of the input by the same check
    used for requirements, but every meaningful word must be present (a label is short, so a partial match is a
    paraphrase). Everything else is "inferred". A value the recruiter set by answering a question keeps
    source "recruiter" (Confirmed by you). The evidence quote is replaced by the real sentence when stated."""
    sentences = _sentences(raw_input)
    for field_value in (
        understanding.primary_candidate_identity,
        understanding.role_interpretation,
        understanding.seniority_scope,
        understanding.candidate_archetype,
    ):
        if not field_value.value or field_value.source == "recruiter":
            continue
        sentence = stated_evidence(field_value.value, sentences, min_share=1.0)
        if sentence:
            field_value.source = "explicit"
            field_value.evidence = sentence
        else:
            field_value.source = "inferred"


def attach_requirement_evidence(decision: IntakeDecision, raw_input: str) -> None:
    """Fills FinalSearchIntentDraft.evidence: requirement text -> the input sentence that states it. A requirement
    with no entry is inferred."""
    draft = decision.final_search_intent
    sentences = _sentences(raw_input)
    evidence: Dict[str, str] = {}
    for requirement in [*draft.hard_requirements, *draft.strong_signals, *draft.preferred_differentiators]:
        sentence = stated_evidence(requirement, sentences)
        if sentence:
            evidence[requirement] = sentence
    draft.evidence = evidence
