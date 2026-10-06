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

Generic structural checks (no role, path name or number is known to the code; they run from the two source texts and the
intent alone). Each emits an ERROR diagnostic:

    path_requirement_leakage      a REQUIRED requirement is applied to a path (inherited from the global intent, or placed in
                                  the wrong path) although the sources state it only for other paths. A path is located in
                                  the sources by its `id`, which is the name the source gives it; a source line is attributed
                                  to a path when it names the path, or sits under a heading that does, and negated lines
                                  ("does NOT require") never count as stating a requirement. An unnamed path is not checked.
    reconciliation_conflict       the intent records that the brief waived / narrowed / contradicted a JD item but still
                                  carries a matching REQUIRED atom for the scope concerned
    unsupported_level             a seniority level (value or alternative) is stated nowhere in the sources, or only for
                                  other paths: a model-generated alternative, never promoted
    country_city_misrepresentation  a country in `entries` (a place below country level) or a city in `countries`
    place_not_in_source           a place named in a location appears in neither source
    remote_unsupported            remote "allowed" with no non-negated source line about remote work for that scope

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
ERROR_CODES = {"path_requirement_leakage", "reconciliation_conflict", "unsupported_level", "country_city_misrepresentation",
               "place_not_in_source", "remote_unsupported"}
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
        return row(ref, "location", ", ".join([*loc.countries, *loc.entries]), loc.strength, loc.basis, scope)

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

    # derived reconciliation label for atoms an explicit reconciliation touches
    for r in rows:
        for rec, rr in zip(intent.reconciliations, rec_rows):
            if r["kind"] in ("skill", "domain", "seniority", "evidence_signal") and _topic_matches(rec.topic, r["text"]) and \
                    (rec.path_id is None or rec.path_id == r["scope"]):
                r["label"] = f"{rec.action}_by_brief"
                break

    for code, ref, detail in scope_checks(intent, jd, brief, rows):
        diag(code, ref, detail)

    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    errors: Dict[str, int] = {}
    for d in diags:
        if d["code"] in ERROR_CODES:
            errors[d["code"]] = errors.get(d["code"], 0) + 1
    # "located" = some source line OPENS with the path's designator (a heading, or "Path B requires ..."). Merely appearing
    # in the text is not enough: a descriptive slug such as "domain-led" appears in prose but is not how the source names a path.
    openers = [_BULLET.sub("", raw).strip() for raw in (jd + "\n" + brief).splitlines()]
    located = {p.id: any(_word(p.id).match(line) for line in openers if line) for p in intent.sourcing_paths}
    return {"atoms": rows, "status_counts": counts, "reconciliations": rec_rows, "diagnostics": diags, "errors": errors, "paths_located": located}


# ---------------------------------------------------------------------------- generic scope checks

_NEGATION = re.compile(r"\b(not|no|never|without|neither|nor|cannot)\b|n't\b", re.I)
_BULLET = re.compile(r"^\s*(?:[-*\u2022\u00b7]|\d+[.)])\s*")
_REMOTE = re.compile(r"\b(remote|remotely|work[- ]from[- ]home|wfh|telecommut\w*)\b", re.I)
_SCOPED_KINDS = ("skill", "experience", "seniority", "location", "domain")


def _word(term: str) -> "re.Pattern[str]":
    """Whole-word, case-insensitive. Separators in a slug-style id ("path-b") match any run of space / - / _ so a model's
    slug of the source's own name ("Path B") still locates it."""
    parts = [re.escape(t) for t in re.split(r"[-_\s]+", term.strip()) if t]
    return re.compile(rf"(?<![A-Za-z0-9]){'[-_ ]+'.join(parts)}(?![A-Za-z0-9])", re.I)


def source_lines(text: str, names: Dict[str, "re.Pattern[str]"]) -> List[Dict[str, Any]]:
    """Each non-empty source line with the paths it is attributed to (None = unscoped overview). A line is attributed to a
    path when it names it; a short heading that opens with a path's name keeps attributing the lines below it until the next
    path heading or an ALL-CAPS heading. The heuristic is deliberately plain and its limits are documented, not hidden: prose
    below a path's section that is not marked as a new section stays attributed to that path."""
    out: List[Dict[str, Any]] = []
    current: Optional[Set[str]] = None
    for raw in (text or "").splitlines():
        line = _BULLET.sub("", raw).strip()
        if not line:
            continue
        named = {pid for pid, rx in names.items() if rx.search(line)}
        letters = [c for c in line if c.isalpha()]
        caps = len(letters) >= 6 and sum(c.isupper() for c in letters) / len(letters) >= 0.8
        if named and len(line) <= 100 and not line.endswith(".") and any(names[pid].match(line) for pid in named):
            current, attributed = set(named), set(named)
        elif named:
            attributed = set(named)
        elif caps:
            current, attributed = None, None
        else:
            attributed = set(current) if current else None
        out.append({"text": line, "paths": attributed, "negated": bool(_NEGATION.search(line))})
    return out


def _probe(atom: Dict[str, Any]) -> List[str]:
    """Words that must appear for a source line to state this atom (any one probe is enough)."""
    if atom["kind"] == "location":
        return [p.split(",")[0].strip() for p in atom["text"].split(", ") if p.strip()]
    return [atom["text"]]


def _stated_for(atom: Dict[str, Any], lines: List[Dict[str, Any]]) -> Set[str]:
    """The named paths whose own (non-negated) source lines state the atom."""
    found: Set[str] = set()
    for ln in lines:
        if ln["negated"] or not ln["paths"]:
            continue
        for probe in _probe(atom):
            if atom["kind"] in ("seniority", "location"):
                hit = bool(_word(probe).search(ln["text"]))
            else:
                hit = bool(stated_evidence(probe, [ln["text"]]))
            if hit:
                found |= ln["paths"]
                break
    return found


def _inherits(intent: ExperimentalHiringIntent, atom: Dict[str, Any]) -> Set[str]:
    """The path ids an atom actually applies to once overrides are resolved."""
    ids = {p.id for p in intent.sourcing_paths}
    if atom["scope"] is not None:
        return {atom["scope"]}
    out = set()
    for p in intent.sourcing_paths:
        overridden = {
            "skill": any(sk.name.strip().lower() == atom["text"].strip().lower() for sk in p.skills),
            "domain": any(d.name.strip().lower() == atom["text"].strip().lower() for d in p.domain),
            "seniority": p.seniority is not None, "experience": p.experience is not None, "location": p.location is not None,
        }.get(atom["kind"], False)
        if not overridden:
            out.add(p.id)
    return out & ids


def scope_checks(intent: ExperimentalHiringIntent, jd: str, brief: str, rows: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    found: List[Tuple[str, str, str]] = []
    paths = list(intent.sourcing_paths)
    openers = [_BULLET.sub("", raw).strip() for raw in (jd + "\n" + brief).splitlines()]
    names = {p.id: _word(p.id) for p in paths if any(_word(p.id).match(line) for line in openers if line)}
    lines = source_lines(jd, names) + source_lines(brief, names)
    sources = jd + "\n" + brief
    atoms = list(iter_atoms(intent))

    # --- path requirement leakage / unsupported levels (need >= 2 paths located in the sources)
    for a in atoms:
        applies = _inherits(intent, a) & set(names) if paths else set()
        if a["kind"] in _SCOPED_KINDS and a["constraint"] and a["kind"] != "seniority" and len(names) >= 2:
            stated = _stated_for(a, lines)
            leaked = sorted(applies - stated) if stated else []
            if leaked:
                found.append(("path_requirement_leakage", a["ref"],
                              f"{a['kind']} {a['text']!r} is required for {sorted(applies)} but the sources state it only for {sorted(stated)}; leaked to {leaked}"))
    for ref, sen, scope in _seniority_holders(intent):
        for level in [sen.value, *sen.alternatives]:
            pat = _word(level)
            mentions = [ln for ln in source_lines(jd, names) + source_lines(brief, names) if pat.search(ln["text"]) and not ln["negated"]]
            if not mentions:
                found.append(("unsupported_level", ref, f"level {level!r} is stated nowhere in the sources (model-generated)"))
                continue
            stated = set().union(*[ln["paths"] for ln in mentions if ln["paths"]]) if any(ln["paths"] for ln in mentions) else set()
            applies = ({scope} if scope else {p.id for p in paths if p.seniority is None}) & set(names)
            if stated and len(names) >= 2 and applies - stated:
                found.append(("unsupported_level", ref, f"level {level!r} is stated only for {sorted(stated)} but is used for {sorted(applies - stated)}"))

    # --- geography typing and support
    components = {part.strip().casefold() for loc in _locations(intent) for e in loc[1].entries if "," in e for part in [e.split(",")[-1]]}
    cities = {e.split(",")[0].strip().casefold() for loc in _locations(intent) for e in loc[1].entries if "," in e}
    countries_all = {c.strip().casefold() for loc in _locations(intent) for c in loc[1].countries}
    for ref, loc, scope in _locations(intent):
        for e in loc.entries:
            if "," not in e and e.strip().casefold() in (components | countries_all):
                found.append(("country_city_misrepresentation", ref, f"{e!r} is a country but sits in `entries` (places below country level)"))
        for c in loc.countries:
            if "," in c or c.strip().casefold() in cities:
                found.append(("country_city_misrepresentation", ref, f"{c!r} is not a country-wide area but sits in `countries`"))
        for place in [*(e.split(",")[0] for e in loc.entries), *loc.countries]:
            if place.strip() and not _word(place).search(sources):
                found.append(("place_not_in_source", ref, f"{place!r} appears in neither source"))
        if loc.remote == "allowed":
            remote_lines = [ln for ln in lines_all(jd, brief, names) if _REMOTE.search(ln["text"]) and not ln["negated"]]
            stated = set().union(*[ln["paths"] for ln in remote_lines if ln["paths"]]) if any(ln["paths"] for ln in remote_lines) else set()
            if not remote_lines:
                found.append(("remote_unsupported", ref, "remote is 'allowed' but no source line says remote work is acceptable"))
            elif scope and stated and scope in names and scope not in stated:
                found.append(("remote_unsupported", ref, f"remote is 'allowed' for {scope!r} but the sources state it only for {sorted(stated)}"))

    # --- reconciliation conflicts
    for i, rec in enumerate(intent.reconciliations):
        if rec.action == "unresolved" or not quote_in(rec.jd_quote, jd):
            continue  # an unresolved conflict is surfaced, not silently resolved; an unverified quote is reported elsewhere
        for a in atoms:
            if a["kind"] not in ("skill", "skill_any_of", "domain", "evidence_signal", "seniority", "experience", "education") or a["strength"] != "required":
                continue
            if rec.path_id is not None:
                scope_ok = a["scope"] == rec.path_id or (a["scope"] is None and rec.path_id in _inherits(intent, a))
            else:
                scope_ok = True
            if not scope_ok or not _topic_matches(rec.topic, a["text"]):
                continue
            if rec.action == "narrowed" and a["basis"] is not None and "recruiter_brief" in a["basis"].sources:
                continue  # the atom already cites the brief: it is the narrowed form
            found.append(("reconciliation_conflict", a["ref"],
                          f"reconciliations[{i}] records {rec.topic!r} as {rec.action}" + (f" for {rec.path_id!r}" if rec.path_id else "") +
                          f" but {a['kind']} {a['text']!r} is still a required atom for that scope"))
    return found


def lines_all(jd: str, brief: str, names: Dict[str, "re.Pattern[str]"]) -> List[Dict[str, Any]]:
    return source_lines(jd, names) + source_lines(brief, names)


def _seniority_holders(intent: ExperimentalHiringIntent):
    if intent.seniority:
        yield "seniority", intent.seniority, None
    for p in intent.sourcing_paths:
        if p.seniority:
            yield f"paths[{p.id}].seniority", p.seniority, p.id


def _locations(intent: ExperimentalHiringIntent):
    if intent.location:
        yield "location", intent.location, None
    for p in intent.sourcing_paths:
        if p.location:
            yield f"paths[{p.id}].location", p.location, p.id
