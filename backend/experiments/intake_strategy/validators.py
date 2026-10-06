"""Deterministic validation of an ExperimentalHiringIntent against its two source texts (EXPERIMENT ONLY).

The model CLAIMS where an atom came from (`basis`) and what the brief did to the JD (`reconciliations`). Code decides
whether that claim holds. Three outcomes are kept apart, never blended:

    claimed     the model's own `basis.sources`
    verified    code found the quote verbatim in a source ("verified"), or found most of the atom's words together in
                one sentence of a source ("lexical", the repo's existing stated-evidence rule)
    unsupported nothing in either source backs the claim; or the atom is `inferred` (stated nowhere, by definition)

Also checked, deterministically: the quote sits in the source the model named (else "misattributed"); a waiver /
narrowing the model recorded was actually applied to the path it names; a JD item the brief contradicted does not
survive as a required atom; an inferred atom is never required; path ids are unique and referenced paths exist.

"verified" means the quote exists verbatim in the cited source and was cited to the right one. It does NOT mean the quote
entails the atom: `quote_overlap` (share of the atom's meaningful words found in its quote) is reported per atom as an
informational signal only, because a faithful paraphrase scores low and a deterministic check cannot tell it from a
mismatch. It never changes a status or a verdict.

Known limit, reported not tuned away: lexical support misses faithful paraphrases, and "approved_knowledge" claims
cannot be checked here at all, so they are reported as unverified.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from backend.experiments.intake_strategy.experimental_schema import (
    Basis,
    ExperimentalHiringIntent,
    effective_view,
)
from backend.services.requirement_provenance import _meaningful, _present, _sentences, _tokens, stated_evidence

WEAK_OVERLAP = 0.34  # informational threshold only
_QUOTE_MARKS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})
_ELLIPSIS = re.compile(r"…|\.\.\.")


def _norm(text: str) -> str:
    text = (text or "").translate(_QUOTE_MARKS).casefold()
    text = re.sub(r"(?m)^[\s\-*\u2022]+", " ", text)  # list bullets at line starts
    return re.sub(r"\s+", " ", text).strip(" \"'")


def quote_in(quote: Optional[str], source_text: str) -> bool:
    """Verbatim (whitespace/case/quote-mark insensitive) presence. A quote with an ellipsis is checked segment by segment,
    in order."""
    if not quote or not quote.strip():
        return False
    haystack, cursor = _norm(source_text), 0
    for segment in _ELLIPSIS.split(quote):
        segment = _norm(segment)
        if len(segment) < 6:
            continue
        found = haystack.find(segment, cursor)
        if found < 0:
            return False
        cursor = found + len(segment)
    return cursor > 0


def _lexical(text: str, sentences: List[str], kind: str) -> bool:
    probe = text.split(",")[0] if kind == "location" else text
    return bool(stated_evidence(probe, sentences))


# ---------------------------------------------------------------------------- atoms


def iter_atoms(intent: ExperimentalHiringIntent) -> Iterator[Dict[str, Any]]:
    """Every claim-bearing atom, global and path-scoped, with its text, strength and basis."""

    def row(ref: str, kind: str, text: str, strength: str, basis: Optional[Basis], scope: Optional[str], hard: Optional[bool] = None) -> Dict[str, Any]:
        return {"ref": ref, "kind": kind, "text": text, "strength": strength, "basis": basis, "scope": scope,
                "constraint": (strength == "required") if hard is None else hard}

    def seniority(s, ref, scope):
        return row(ref, "seniority", s.value, s.strength, s.basis, scope)

    def experience(e, ref, scope):
        years = f"{e.minimum_years}+ years" if e.minimum_years is not None else f"up to {e.maximum_years} years"
        return row(ref, "experience", years, e.strength, e.basis, scope)

    def location(loc, ref, scope):
        return row(ref, "location", ", ".join(loc.entries), loc.strength, loc.basis, scope)

    scopes: List[Tuple[Optional[str], str, Any]] = [(None, "", intent)]
    for p in intent.sourcing_paths:
        scopes.append((p.id, f"paths[{p.id}].", p))
        yield row(f"paths[{p.id}]", "path", p.label, "required", p.basis, p.id, hard=True)

    for scope, prefix, holder in scopes:
        if holder.seniority:
            yield seniority(holder.seniority, f"{prefix}seniority", scope)
        if holder.experience:
            yield experience(holder.experience, f"{prefix}experience", scope)
        if holder.location:
            yield location(holder.location, f"{prefix}location", scope)
        for i, s in enumerate(holder.skills):
            yield row(f"{prefix}skills[{i}]", "skill", s.name, s.strength, s.basis, scope)
        for i, d in enumerate(holder.domain):
            yield row(f"{prefix}domain[{i}]", "domain", d.name, d.strength, d.basis, scope)
    for i, g in enumerate(intent.skill_any_of):
        yield row(f"skill_any_of[{i}]", "skill_any_of", " or ".join(g.any_of), g.strength, g.basis, None)
    for i, c in enumerate(intent.companies):
        yield row(f"companies[{i}]", "company", c.name, c.strength, c.basis, None)
    if intent.education:
        yield row("education", "education", ", ".join(intent.education.degrees + intent.education.streams), intent.education.strength, intent.education.basis, None)
    for i, x in enumerate(intent.exclusions):
        yield row(f"exclusions[{i}]", f"exclusion:{x.kind}", x.value, "required", x.basis, None, hard=True)
    for i, x in enumerate(intent.semantic_exclusions):
        yield row(f"semantic_exclusions[{i}]", "semantic_exclusion", x.concept, "required", x.basis, None, hard=True)
    for i, e in enumerate(intent.evidence_signals):
        yield row(f"evidence_signals[{i}]", "evidence_signal", e.name, e.strength, e.basis, None)


# ---------------------------------------------------------------------------- provenance


def _verify_atom(atom: Dict[str, Any], jd: str, brief: str, jd_sentences: List[str], brief_sentences: List[str]) -> Dict[str, Any]:
    basis: Optional[Basis] = atom["basis"]
    out = {k: atom[k] for k in ("ref", "kind", "text", "strength", "scope", "constraint")}
    if basis is None:
        return {**out, "claimed": [], "verified": [], "status": "missing", "label": "unattributed"}
    claimed = list(dict.fromkeys(basis.sources))
    texts = {"jd": (jd, jd_sentences), "recruiter_brief": (brief, brief_sentences)}
    verbatim = {s for s, (t, _) in texts.items() if quote_in(basis.quote, t)}
    lexical = {s for s, (_, sent) in texts.items() if _lexical(atom["text"], sent, atom["kind"]) or
               (basis.quote and bool(stated_evidence(basis.quote, sent)))}
    found = verbatim | lexical
    stated_claims = [s for s in claimed if s in texts]
    if claimed == ["inferred"]:
        status, verified = "inferred", []
    elif found and not (set(stated_claims) & found) and stated_claims:
        status, verified = "misattributed", sorted(found)
    elif set(stated_claims) & verbatim:
        status, verified = "verified", sorted(set(stated_claims) & found)
    elif set(stated_claims) & lexical:
        status, verified = "lexical", sorted(set(stated_claims) & lexical)
    elif "approved_knowledge" in claimed:
        status, verified = "approved_unverified", []
    else:
        status, verified = "unsupported", []
    quote_found = bool(verbatim)
    if basis.quote and not quote_found:
        out["quote_not_found"] = True
    words = _meaningful(atom["text"])
    if basis.quote and words:
        qtoks = _tokens(basis.quote)
        out["quote_overlap"] = round(sum(1 for w in words if _present(w, qtoks)) / len(words), 2)
    # Derived by code from where support was FOUND (either source), not from what the model cited.
    seen = sorted(found) if status in ("verified", "lexical") else verified
    if status == "inferred":
        label = "inferred"
    elif set(seen) == {"jd", "recruiter_brief"}:
        label = "stated_in_both"
    elif seen == ["jd"]:
        label = "retained_from_jd"
    elif seen == ["recruiter_brief"]:
        label = "added_by_brief"
    else:
        label = "unsupported"
    return {**out, "claimed": claimed, "verified": verified, "status": status, "label": label}


def _topic_matches(topic: str, text: str, share: float = 0.75) -> bool:
    words = _meaningful(topic)
    if not words:
        return False
    toks = _tokens(text)
    return sum(1 for w in words if _present(w, toks)) / len(words) >= share


def validate(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Dict[str, Any]:
    jd_s, brief_s = _sentences(jd), _sentences(brief)
    rows = [_verify_atom(a, jd, brief, jd_s, brief_s) for a in iter_atoms(intent)]
    diags: List[Dict[str, str]] = []

    def diag(code: str, ref: str, detail: str) -> None:
        diags.append({"code": code, "ref": ref, "detail": detail})

    for r in rows:
        if r["status"] == "missing" and (r["constraint"] or r["kind"] in ("skill", "domain", "seniority", "experience", "location", "path")):
            diag("basis_missing", r["ref"], f"{r['kind']} {r['text']!r}/{r['strength']} carries no basis")
        elif r["status"] == "unsupported":
            diag("claim_unsupported", r["ref"], f"{r['kind']} {r['text']!r}: claimed {r['claimed']}, nothing in either source backs it")
        elif r["status"] == "misattributed":
            diag("source_misattributed", r["ref"], f"{r['text']!r}: claimed {r['claimed']} but found in {r['verified']}")
        elif r["status"] == "approved_unverified":
            diag("approved_knowledge_unverified", r["ref"], f"{r['text']!r}: approved_knowledge cannot be verified here")
        if r["status"] == "inferred" and r["constraint"]:
            diag("inferred_hard_constraint", r["ref"], f"{r['kind']} {r['text']!r} is required but inferred (stated nowhere)")
        if r.get("quote_overlap") is not None and r["quote_overlap"] < WEAK_OVERLAP:
            diag("quote_weakly_related", r["ref"], f"{r['text']!r}: only {r['quote_overlap']:.0%} of its words appear in its quote (informational)")
        if r.get("quote_not_found") and r["status"] not in ("missing", "inferred"):
            diag("quote_not_found", r["ref"], f"{r['text']!r}: the quote is not verbatim in either source")

    # structural
    ids = [p.id for p in intent.sourcing_paths]
    if len(ids) != len(set(ids)):
        diag("duplicate_path_id", "sourcing_paths", f"ids={ids}")
    if len(ids) == 1:
        diag("single_path", "sourcing_paths", "one path adds nothing over the global intent")

    # reconciliations
    rec_rows: List[Dict[str, Any]] = []
    for i, rec in enumerate(intent.reconciliations):
        ref = f"reconciliations[{i}]"
        jd_ok, brief_ok = quote_in(rec.jd_quote, jd), quote_in(rec.brief_quote, brief)
        rec_rows.append({"ref": ref, "topic": rec.topic, "action": rec.action, "path_id": rec.path_id, "result": rec.result,
                         "jd_quote_verified": jd_ok, "brief_quote_verified": brief_ok})
        if rec.path_id is not None and rec.path_id not in ids:
            diag("reconciliation_unknown_path", ref, f"path_id={rec.path_id!r} not in {ids}")
        if not jd_ok:
            diag("reconciliation_jd_quote_unverified", ref, f"{rec.topic!r}: jd_quote not verbatim in the JD")
        if not brief_ok:
            diag("reconciliation_brief_quote_unverified", ref, f"{rec.topic!r}: brief_quote not verbatim in the brief")
        # A waiver/narrowing the model recorded must actually be applied where it says.
        if rec.action in ("waived", "narrowed") and rec.path_id in ids:
            view = effective_view(intent, rec.path_id)
            still = [s for s in view["skills"] if _topic_matches(rec.topic, s.name) and s.strength == "required"]
            if still:
                diag("waiver_not_applied", ref, f"{rec.action} {rec.topic!r} on path {rec.path_id!r} but the path still requires {[s.name for s in still]}")
        # A JD item the brief contradicted must not survive as a required atom.
        if rec.action == "contradicted":
            alive = [a for a in rows if a["strength"] == "required" and a["kind"] in ("skill", "domain", "evidence_signal")
                     and _topic_matches(rec.topic, a["text"])]
            if alive:
                diag("contradicted_item_survives", ref, f"{rec.topic!r} contradicted but still required: {[a['text'] for a in alive]}")

    # derived reconciliation label for atoms an explicit reconciliation touches
    for r in rows:
        for rec, rr in zip(intent.reconciliations, rec_rows):
            if r["kind"] in ("skill", "domain", "seniority", "evidence_signal") and _topic_matches(rec.topic, r["text"]) and \
                    (rec.path_id is None or rec.path_id == r["scope"]):
                r["label"] = f"{rec.action}_by_brief"
                break

    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"atoms": rows, "status_counts": counts, "reconciliations": rec_rows, "diagnostics": diags}
