"""The Evidence Check: the semantic unit the Judge evaluates (offline; deterministic; no provider, no model).

    StructuredHiringIntent -> Compiler -> DownstreamContext -> JudgeChecklist -> **Evidence Checks** -> Judge -> Admission

An Evidence Check is a DOWNSTREAM EXECUTION ARTIFACT. It is not part of `StructuredHiringIntent`: it is built from the compiled checklist, per path, and only
the Judge reads it. One check = one semantic claim = one `check_id`:

  positive   "the candidate evidences <criterion>": a skill; a skill AT a depth (skill + proficiency is ONE claim); a prose capability
  negative   "the candidate is NOT <excluded work identity>": an explicit predicate (what must not be indicated, what never suffices, what clears it)

The Judge must not rebuild a claim from recruiter prose. Everything it needs is in the check: the criterion text (positives), the predicate (negatives),
and the deterministic binding rules that decide whether a quote supports THIS check and not a neighbouring one:

  * subject binding      a named skill's quote must contain that skill (evidence for Python is never evidence for Java);
  * work-evidence        a skill AT a depth needs demonstrated work or a certification (a skills-list entry, a title or a headline is "a skill quote alone");
  * indicator binding    a PRESENT exclusion's quote must contain one of the predicate's own indicator terms;
  * quote gate           exact, contiguous, no ellipsis, inside ONE supplied passage (`verify_quote`).

Exclusion results are three-state: PRESENT / NOT_PRESENT / INSUFFICIENT_EVIDENCE. Nothing here ever turns INSUFFICIENT_EVIDENCE into NOT_PRESENT.
See backend/services/DOWNSTREAM_CONSUMER_CONTRACT.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

POSITIVE, NEGATIVE = "positive", "negative"
PRESENT, NOT_PRESENT, INSUFFICIENT_EVIDENCE = "PRESENT", "NOT_PRESENT", "INSUFFICIENT_EVIDENCE"
EXCLUSION_STATES = (PRESENT, NOT_PRESENT, INSUFFICIENT_EVIDENCE)

# quote-verification failures that justify the ONE narrow retry (a binding failure is a discard, not a retry)
RETRIABLE_QUOTE_FAILURES = ("ellipsis", "quote_not_found", "quote_too_short", "no_passage")
WORK_EVIDENCE_TYPES = ("demonstrated_work", "certification")

PREDICATE_KNOWLEDGE_VERSION = "exclusion-predicates-v1-2026-10-07"

_I = re.IGNORECASE


# ======================================================================================================================
# the schema
# ======================================================================================================================


@dataclass(frozen=True)
class EvidenceCheck:
    check_id: str                         # unique per path: the ONLY key a verdict may bind to
    path_id: Optional[str]
    concept: str                          # skill | skill.proficiency | skill_any_of | evidence_signal | domain | ... | semantic_exclusion
    kind: str                             # skill | proficiency | any_of | prose | legacy | exclusion
    criterion: str                        # positives: the exact claim the model is asked about. negatives: a one-line description (the model is given the predicate)
    label: str                            # the stable text key of the existing judgments / alignment (the checklist item text)
    polarity: str                         # positive | negative
    tier: Optional[str]
    strength: Optional[str]
    proficiency: Optional[str]            # hands_on | working_knowledge | advanced | None
    relationship: Optional[str]           # None = unspecified (never read as current)
    provenance: Dict[str, Any]
    proficiency_source: Optional[str] = None      # None | "intent" | "stated_in_criterion_text" (a depth PHRASE in the criterion; never inferred from a verb)
    subject: Optional[str] = None                 # the skill / tool the claim is about
    subject_terms: Tuple[str, ...] = ()           # deterministic subject binding tokens ("" = no deterministic binding for this check)
    requires_work_evidence: bool = False          # a depth claim needs demonstrated work or a certification
    predicate: Optional[Dict[str, Any]] = None    # negatives only
    recruiter_wording: str = ""                   # negatives: the original wording, kept for audit only and NEVER sent to the model

    def to_dict(self) -> Dict[str, Any]:
        return {"check_id": self.check_id, "path_id": self.path_id, "concept": self.concept, "kind": self.kind, "criterion": self.criterion, "label": self.label,
                "polarity": self.polarity, "tier": self.tier, "strength": self.strength, "proficiency": self.proficiency, "proficiency_source": self.proficiency_source,
                "relationship": self.relationship, "provenance": dict(self.provenance), "subject": self.subject, "subject_terms": list(self.subject_terms),
                "requires_work_evidence": self.requires_work_evidence, "predicate": self.predicate, "recruiter_wording": self.recruiter_wording}


# ======================================================================================================================
# proficiency: the complete claim is "skill + depth"
# ======================================================================================================================

DEPTH_CLAUSE = {
    "hands_on": "at the level of hands-on use. The candidate has personally built, written or operated {s} in real work. Listing {s} as a skill, having studied it, or "
                "working beside people who use it is not hands-on use.",
    "working_knowledge": "at the level of working knowledge. The candidate has practical familiarity with {s} from actual use. Expert depth is not required; a listed "
                         "skill or a course alone is not enough.",
    "advanced": "at the level of advanced proficiency. The candidate shows depth beyond routine use of {s} (stated expertise, or sophisticated work built with it). "
                "Routine or basic use is not advanced.",
}
# an EXPLICIT depth phrase at the head of a criterion sentence ("Working knowledge of X"): lifted into the check's proficiency. A verb ("built", "developed") never is.
_LEAD_DEPTH = re.compile(r"^\s*(?P<d>working knowledge of|hands[- ]on|advanced proficiency in|advanced|expert(?:ise)? in)\s+(?P<s>.+?)\s*$", _I)
_LEAD_DEPTH_MAP = {"working knowledge of": "working_knowledge", "advanced proficiency in": "advanced", "advanced": "advanced", "expertise in": "advanced", "expert in": "advanced"}

_STOP = {"the", "and", "of", "or", "a", "an", "in", "for", "to", "with", "microsoft", "ms"}
_GENERIC_ALT = re.compile(r"^\s*(?:similar|comparable|equivalent|related|other|any|modern)\b", _I)


def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-z0-9][a-z0-9+#./&-]*", (s or "").casefold())


def _word_in(token: str, text_tokens: set) -> bool:
    return token in text_tokens or (token.endswith("s") and token[:-1] in text_tokens) or (token + "s") in text_tokens


def subject_tokens(subject: str) -> Tuple[str, ...]:
    return tuple(t for t in _tokens(subject) if t not in _STOP)


def subject_in(quote: str, tokens: Tuple[str, ...]) -> bool:
    """Deterministic subject binding: every significant token of the subject appears in the quote as a whole word (plural tolerant)."""
    if not tokens:
        return True
    have = set(_tokens(quote))
    return all(_word_in(t, have) for t in tokens)


def _bindable(subject: str) -> bool:
    """Only a NAMED tool / skill (one or two significant tokens) is bound lexically. A category ("Modern Data Platforms", "Distributed Systems") is evidenced by
    its members, so a lexical rule would discard valid evidence; those checks rely on the model and the review pass (a documented limit)."""
    toks = subject_tokens(subject)
    return 1 <= len(toks) <= 2 and not _GENERIC_ALT.match(subject or "")


# ======================================================================================================================
# quote verification (the gate; not weakened)
# ======================================================================================================================

_PUNCT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", " ": " ", "•": " ", "·": " ", "▪": " ", "‣": " "})


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_PUNCT)).strip().casefold()


def verify_quote(quote: str, passage_text: Optional[str]) -> Tuple[bool, str]:
    """A quote is evidence only if it is ONE contiguous span copied from ONE supplied passage. No ellipsis (`...` or the single character), no paraphrase, no
    fabrication, no span stitched from two places. Returns (ok, reason); reason is one of RETRIABLE_QUOTE_FAILURES when not ok."""
    q = (quote or "").strip()
    if passage_text is None:
        return False, "no_passage"
    if len(q) < 3:
        return False, "quote_too_short"
    if "..." in q or "…" in q:
        return False, "ellipsis"
    if _fold(q) not in _fold(passage_text):
        return False, "quote_not_found"
    return True, "ok"


def validate_binding(check: EvidenceCheck, quote: str, evidence_type: Optional[str], label: str = "") -> Optional[str]:
    """None when the (already verified) quote supports THIS check; else the reason it does not. Deterministic."""
    if check.polarity == POSITIVE:
        if label == "career dates":
            return None                                                       # a computed passage (the duration claim), never model-quoted
        if check.requires_work_evidence and evidence_type not in WORK_EVIDENCE_TYPES:
            return "binding:work_evidence_required"
        if check.subject_terms and not subject_in(quote, check.subject_terms):
            return "binding:subject_not_in_quote"
        return None
    terms = tuple((check.predicate or {}).get("evidence_terms") or ())
    if terms and not any(subject_in(quote, subject_tokens(t)) for t in terms):
        return "binding:indicator_not_in_quote"
    return None


# ======================================================================================================================
# positive checks
# ======================================================================================================================


def _split_list(s: str) -> List[str]:
    parts = re.split(r",\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and\s+", s or "")
    return [p.strip(" .;") for p in parts if p and p.strip(" .;")]


def _subject_for(concept: str, value: str, label: str) -> Tuple[Optional[str], List[str]]:
    """(subject, alternatives) of a positive item, from the compiled atom's own value."""
    if concept == "skill":
        return value or label, []
    if concept == "skill.proficiency":
        return (value.split(" = ", 1)[0] if " = " in (value or "") else (value or label)), []
    if concept == "skill_any_of":
        alts = [a.strip() for a in (value or label).split("|") if a.strip()]
        return " or ".join(alts), alts
    return None, []


def _positive(item: Any, ctx_path: Optional[str], tier: Optional[str], label: str) -> EvidenceCheck:
    concept = item.concept
    value = getattr(item, "value", "") or ""
    subject, alts = _subject_for(concept, value, label)
    proficiency, psource = item.proficiency, ("intent" if item.proficiency else None)
    kind = "prose"
    if concept == "skill":
        kind = "skill"
    elif concept == "skill.proficiency":
        kind = "proficiency"
    elif concept == "skill_any_of":
        kind = "any_of"
    criterion = label
    if kind == "prose":
        m = _LEAD_DEPTH.match(label)
        if m:                                                                  # an explicit depth PHRASE stated in the criterion text itself
            d = m.group("d").casefold().replace("hands on", "hands-on")
            proficiency = "hands_on" if d.startswith("hands") else _LEAD_DEPTH_MAP.get(d)
            if proficiency:
                psource, subject = "stated_in_criterion_text", m.group("s")
    if proficiency and kind in ("proficiency", "prose") and subject:
        criterion = f"{label}, {DEPTH_CLAUSE[proficiency].format(s=subject)}" if kind == "prose" else f"{subject}, {DEPTH_CLAUSE[proficiency].format(s=subject)}"
    elif kind == "any_of":
        criterion = "Any one of: " + "; ".join(alts) if alts else label
    terms: Tuple[str, ...] = ()
    if kind in ("skill", "proficiency") and subject and _bindable(subject):
        terms = subject_tokens(subject)
    elif kind == "any_of" and alts and all(_bindable(a) for a in alts):
        terms = ()                                                             # alternatives: bound per-alternative by the model; no single token set applies
    return EvidenceCheck(
        check_id=f"{ctx_path or 'global'}#{item.item_id}|{tier or 'differentiator'}", path_id=ctx_path, concept=concept, kind=kind, criterion=criterion, label=label,
        polarity=POSITIVE, tier=tier, strength=item.strength, proficiency=proficiency, relationship=item.relationship, provenance=dict(item.provenance),
        proficiency_source=psource, subject=subject, subject_terms=terms, requires_work_evidence=bool(proficiency))


def positive_checks(consumer_input: Any) -> List[EvidenceCheck]:
    """One check per (tier, text) the Judge asks, aligned with `consumer_input.judged`. Legacy intents get plain checks (the text is the criterion; no binding)."""
    checks: List[EvidenceCheck] = []
    for i, ((tier, text), item) in enumerate(zip(consumer_input.judged, consumer_input.judged_items)):
        if item is None:
            checks.append(EvidenceCheck(check_id=f"legacy#{tier}[{i}]", path_id=None, concept="legacy_signal", kind="legacy", criterion=text, label=text, polarity=POSITIVE,
                                        tier=tier, strength=None, proficiency=None, relationship=None, provenance={"state": "unrecorded", "sources": [], "quote": None}))
        else:
            checks.append(_positive(item, item.path_id, tier, text))
    return checks


# ======================================================================================================================
# negative checks: explicit semantic predicates
# ======================================================================================================================

_NOT_EQUIV = re.compile(r"^(?P<x>.+?)\s+(?:are|is)\s+not\s+(?:equivalent|equal|the same|a substitute|comparable)\s+(?:to|as|with|for)\s+(?P<y>.+)$", _I)
_ALONE_WITHOUT = re.compile(r"^(?P<x>.+?)\s+(?:alone|only)\s+(?:without|lacking)\s+(?P<y>.+)$", _I)
_EXCL_WITHOUT = re.compile(r"^(?:experience\s+)?exclusively\s+(?:in\s+)?(?P<x>.+?)\s+without\s+(?P<y>.+)$", _I)

# Approved, versioned knowledge (the same status as the role-family taxonomy): the work identity a recruiter's phrase names, spelled out so the Judge is not left to
# infer it, and what NEVER suffices. One validated anchor only; a phrase with no entry gets the structural predicate below (its own words, no expansion).
_PREDICATE_KNOWLEDGE = [
    {"id": "security_operations", "triggers": ["security operations", "cybersecurity operations", "security operations center"],
     "must_not_indicate": ["SOC (security operations center) work", "security operations work",
                           "cybersecurity operations work such as alert monitoring, incident triage, threat hunting or vulnerability management",
                           "equivalent security-operations work"],
     "evidence_terms": ["soc", "security operations", "cybersecurity operations", "siem", "threat hunting", "incident triage", "security monitoring"],
     "not_sufficient": ["working for a security company, security vendor or security firm", "mentioning security or cybersecurity", "having general security experience, security-awareness training or security-related duties",
                        "security work that is not operations work (for example review, audit, compliance or analysis of security data)"]},
]
_ANTI_BROADENING = ["the topic or field merely being mentioned", "the employer or industry being in that field", "adjacent or partly overlapping duties"]


def _knowledge_for(x: str) -> Optional[Dict[str, Any]]:
    norm = " ".join(re.sub(r"[-/]", " ", (x or "").casefold()).split())
    return next((k for k in _PREDICATE_KNOWLEDGE if any(t in norm for t in k["triggers"])), None)


def _evidence_terms(phrases: List[str]) -> List[str]:
    out: List[str] = []
    for p in phrases:
        for t in _tokens(p):
            if len(t) >= 3 and t not in _STOP and t not in out and t not in ("work", "experience", "background", "backgrounds", "generic", "substantive"):
                out.append(t)
    return out


def exclusion_predicate(text: str) -> Dict[str, Any]:
    """The explicit semantic predicate of an exclusion. The recruiter's qualifier is KEPT (a leading "generic", "exclusively", "alone", the "without / not equivalent
    to" clause); nothing is broadened."""
    t = (text or "").strip()
    form, x, y = "profile", t, ""
    for name, rx in (("exclusive_without", _EXCL_WITHOUT), ("alone_without", _ALONE_WITHOUT), ("not_equivalent", _NOT_EQUIV)):
        m = rx.match(t)
        if m:
            form, x, y = name, m.group("x"), m.group("y")
            break
    qualifier = "generic" if re.match(r"^\s*generic\b", x, _I) else None
    unless = _split_list(y) if y else []
    known = _knowledge_for(x) if form != "profile" else None
    if known:
        must, terms, nots, kid = list(known["must_not_indicate"]), list(known["evidence_terms"]), list(known["not_sufficient"]), known["id"]
    elif form == "profile":
        must, terms, nots, kid = [x], _evidence_terms([x]), ["only part of the description matching"], None
    elif form == "alone_without":
        must, terms, nots, kid = [f"only {x}, with no substantive evidence of the work itself"], _evidence_terms([x]), list(_ANTI_BROADENING), None
    else:
        must = _split_list(re.sub(r"^\s*generic\s+", "", x, flags=_I)) or [x]
        terms, nots, kid = _evidence_terms(must), list(_ANTI_BROADENING), None
    return {"subject": "candidate_work_identity", "form": form, "must_not_indicate": must, "exclusive": form == "exclusive_without", "qualifier": qualifier,
            "unless_candidate_also_shows": unless, "not_sufficient": nots, "evidence_terms": terms, "knowledge": ({"id": kid, "version": PREDICATE_KNOWLEDGE_VERSION} if kid else None)}


def model_predicate(p: Dict[str, Any]) -> Dict[str, Any]:
    """What the model is given for a negative check: the predicate only (no recruiter prose, no evidence-term list, no knowledge id)."""
    out = {"subject": p["subject"], "must_not_indicate": p["must_not_indicate"], "not_sufficient": p["not_sufficient"]}
    if p["exclusive"]:
        out["exclusive"] = True
    if p["qualifier"]:
        out["qualifier"] = p["qualifier"]
    if p["unless_candidate_also_shows"]:
        out["unless_candidate_also_shows"] = p["unless_candidate_also_shows"]
    return out


def negative_checks(checklist: Any) -> List[EvidenceCheck]:
    checks: List[EvidenceCheck] = []
    for item in checklist.exclusions:
        pred = exclusion_predicate(item.text)
        checks.append(EvidenceCheck(
            check_id=f"{item.path_id or 'global'}#{item.item_id}|exclusion", path_id=item.path_id, concept=item.concept, kind="exclusion",
            criterion="the candidate's work identity must NOT be: " + "; ".join(pred["must_not_indicate"]), label=item.text, polarity=NEGATIVE, tier=item.tier,
            strength=item.strength, proficiency=None, relationship=None, provenance=dict(item.provenance), predicate=pred, recruiter_wording=item.text))
    return checks
