"""Generic validators added after Role 2 (EXPERIMENT ONLY). Role-agnostic: no role, title, skill, company or number is known here.

These live in their OWN module on purpose. `validators.validate()` (used by the frozen Role 1 and Role 2 evaluations) is unchanged
and byte-identical, so re-evaluating Role 1 / Role 2 stored results cannot move. Roles 3 onward call `validate_cross_role()`, which
is `validate()` plus the five checks below. Each emits an ERROR diagnostic and is justified by an error Role 2 actually produced.

    title_analogy                    a `role_family` title whose ONLY mentions in the sources are comparisons ("more like X",
                                     "similar to X", "resembles X", "like a X"): a reference title is not a target title
    responsibility_only_required     a REQUIRED atom whose supporting source text is only a statement of what the role does
                                     (a responsibility), never a stated qualification or a recruiter selection criterion
    unsupported_current_relationship `relationship = current` although no supporting source text states current / present use
    unsupported_proficiency          a depth (advanced / hands_on / working_knowledge) the cited wording does not state, including
                                     a weaker statement read as a stronger depth
    work_mode_unsupported            a `work_mode` that no non-negated source line states (or states only for other paths)

Responsibility vs qualification is decided by what a line MEANS where it can be told, and by the heading only as a second signal:
a line with explicit selection language (years, degree, "experience with", "proficiency", "ability to", "must", "hands-on", ...) is a
qualification wherever it sits; a line under a responsibilities-style heading without such language is a responsibility; with no
heading at all, an imperative / "you will" / "responsible for" line without selection language is a responsibility. A JD whose
sections are unlabelled is therefore still classified; a JD whose headings are unusual falls back to the sentence form.

Known limits (reported, not tuned away): the checks are lexical. A depth cue elsewhere in a quoted sentence can support the wrong
skill; the imperative-verb list is finite; a requirement phrased as a task ("Build APIs ...") under no heading reads as a
responsibility; `current` cues are English words. Each limit errs toward flagging for review, never toward silently passing.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.validators import _BULLET, _word, iter_atoms, quote_in, source_lines, validate
from backend.services.requirement_provenance import _sentences, stated_evidence

I = re.IGNORECASE
CROSS_ROLE_ERROR_CODES = {"title_analogy", "responsibility_only_required", "unsupported_current_relationship", "unsupported_proficiency", "work_mode_unsupported"}

# ---------------------------------------------------------------------------- title analogy

_ANALOGY_CUE = (
    r"(?:more\s+like|similar\s+to|resembl\w*|akin\s+to|comparable\s+to|reminiscent\s+of|along\s+the\s+lines\s+of|"
    r"in\s+the\s+(?:mold|vein|style)\s+of|(?:someone|somebody|people|a\s+person|a\s+profile|a\s+candidate)\s+like|like\s+(?:a|an|the|our|your)\b)"
)


def _title_rx(title: str) -> Optional[str]:
    tokens = re.findall(r"[A-Za-z0-9+#]+", title)
    if not tokens:
        return None
    tokens[-1] = tokens[-1][:-1] if len(tokens[-1]) > 3 and tokens[-1].lower().endswith("s") else tokens[-1]   # plural or singular either way
    return r"(?<![A-Za-z0-9])" + r"[-\s]+".join(re.escape(t) for t in tokens) + r"s?(?![A-Za-z0-9])"


def _title_analogy(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Iterator[Tuple[str, str, str]]:
    sentences = _sentences(jd) + _sentences(brief)
    for title in intent.role_family:
        rx = _title_rx(title)
        if rx is None:
            continue
        mentions = [s for s in sentences if re.search(rx, s, I)]
        if not mentions:
            continue
        analogy = [s for s in mentions if re.search(rf"{_ANALOGY_CUE}(?:\s+(?:a|an|the|our|your))?(?:\s+[\w'-]+){{0,3}}?\s+{rx[len('(?<![A-Za-z0-9])'):]}", s, I)]
        if len(analogy) == len(mentions):
            yield ("title_analogy", f"role_family[{title}]",
                   f"{title!r} is mentioned only as a comparison ({len(analogy)} of {len(mentions)} mention(s): {analogy[0][:110]!r}); a reference title is not a target title")


# ---------------------------------------------------------------------------- responsibility vs qualification

_HEAD_RESP = re.compile(r"responsibilit|\bduties\b|what you(?:'ll| will) do|key tasks|day[- ]to[- ]day|your role|the role\b", I)
_HEAD_QUAL = re.compile(r"requirement|qualification|\bskills\b|what you(?:'ll| will) bring|who you are|must[- ]have|about you|nice[- ]to[- ]have|preferred|experience required", I)
_SELECTION = re.compile(
    r"\b(\d+\s*\+?\s*years?|degree|bachelor|master|ph\.?d|certif\w*|must|required|requires?|requirements?|minimum|proficien\w*|"
    r"experience (?:with|in|of|working|building|integrating|designing|implementing)|experienced|knowledge of|familiar\w*|expertise in|"
    r"background in|understanding of|ability to|hands-on)\b", I)
_HARD_SELECTION = re.compile(r"\b(must (?:have|be|hold|possess)|(?:is|are) required|required (?:skills?|qualifications?|experience)|minimum (?:of )?\d+|\d+\s*\+?\s*years?|degree|bachelor|master|ph\.?d|certif\w*)\b", I)
_RESP_VERBS = frozenset(
    "partner design develop build drive champion integrate collaborate communicate apply evaluate provide maintain stay help work manage ensure "
    "support prepare review analyze analyse coordinate deliver assist coach mentor contribute create implement identify conduct perform own lead "
    "leverage translate serve oversee monitor optimize optimise define establish report document test deploy foster resolve recommend".split())
_RESP_PHRASE = re.compile(r"\byou(?:'ll| will)\b|\bwill be responsible\b|\bresponsible for\b|\bduties include\b|\bwill (?:work|lead|own|design|build|partner)\b", I)


def classify_lines(text: str) -> List[Dict[str, Any]]:
    """Each non-empty source line as `responsibility`, `qualification` or `other`. See the module docstring for the rule."""
    out: List[Dict[str, Any]] = []
    section: Optional[str] = None
    for raw in (text or "").splitlines():
        line = _BULLET.sub("", raw).strip()
        if not line:
            continue
        is_heading = (not _BULLET.match(raw)) and len(line) <= 80 and not re.search(r"[.;:!?,]$", line) and len(line.split()) <= 8
        if is_heading:
            section = "responsibilities" if _HEAD_RESP.search(line) else "qualifications" if _HEAD_QUAL.search(line) else None
            out.append({"text": line, "kind": "heading"})
            continue
        if section == "responsibilities":
            kind = "qualification" if _HARD_SELECTION.search(line) else "responsibility"
        elif section == "qualifications":
            kind = "qualification"
        elif _SELECTION.search(line):
            kind = "qualification"
        elif _RESP_PHRASE.search(line) or (line.split()[0].lower().strip(",") in _RESP_VERBS):
            kind = "responsibility"
        else:
            kind = "other"
        out.append({"text": line, "kind": kind})
    return out


def _support(text: str, quote: Optional[str], lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The source lines that support an atom: those containing its quote verbatim, else those that lexically state its text."""
    body = [ln for ln in lines if ln["kind"] != "heading"]
    if quote:
        hit = [ln for ln in body if quote_in(quote, ln["text"])]
        if hit:
            return hit
    return [ln for ln in body if stated_evidence(text, [ln["text"]])]


def _responsibility_only(intent: ExperimentalHiringIntent, jd: str, brief: str, rows: List[Dict[str, Any]]) -> Iterator[Tuple[str, str, str]]:
    jd_lines, brief_lines = classify_lines(jd), classify_lines(brief)
    for a in rows:
        if a["strength"] != "required" or a["kind"] not in ("evidence_signal", "skill", "skill_any_of", "domain"):
            continue
        basis = a["basis"]
        quote = basis.quote if basis else None
        if _support(a["text"], quote, brief_lines):
            continue                       # the recruiter brief states it: an explicit selection criterion
        origin = _support(a["text"], quote, jd_lines)
        if not origin or any(ln["kind"] != "responsibility" for ln in origin):
            continue                       # unsupported (provenance's job) or at least partly a qualification / unclassified
        if any(ln["kind"] == "qualification" and stated_evidence(a["text"], [ln["text"]]) for ln in jd_lines):
            continue                       # also stated as a qualification elsewhere
        yield ("responsibility_only_required", a["ref"],
               f"{a['kind']} {a['text']!r} is required but its only source is a statement of what the role does ({origin[0]['text'][:100]!r}); "
               "a responsibility is context unless the sources also state it as a qualification or the brief makes it a selection criterion")


# ---------------------------------------------------------------------------- relationship = current

_CURRENT_CUE = re.compile(r"(?<!stay )(?<!keep )(?<!remain )\b(currently|current|presently|at present|right now|now|present (?:role|position|employer|company|job))\b", I)


def _skill_holders(intent: ExperimentalHiringIntent) -> Iterator[Tuple[str, Any]]:
    for i, s in enumerate(intent.skills):
        yield f"skills[{i}]", s
    for p in intent.sourcing_paths:
        for i, s in enumerate(p.skills):
            yield f"paths[{p.id}].skills[{i}]", s


def _unsupported_current(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Iterator[Tuple[str, str, str]]:
    lines = classify_lines(jd) + classify_lines(brief)

    def check(ref: str, label: str, basis: Any, relationship: str) -> Optional[Tuple[str, str, str]]:
        if relationship != "current" or (basis and "approved_knowledge" in basis.sources):
            return None
        support = _support(label, basis.quote if basis else None, lines)
        texts = [ln["text"] for ln in support] + ([basis.quote] if basis and basis.quote else [])
        if not support or any(_CURRENT_CUE.search(t) for t in texts):
            return None                    # nothing to judge (provenance's job), or a source line does state current / present use
        return ("unsupported_current_relationship", ref,
                f"{label!r} has relationship=current but no supporting source text states current or present use: {support[0]['text'][:100]!r}")

    for ref, s in _skill_holders(intent):
        found = check(ref, s.name, s.basis, s.relationship)
        if found:
            yield found
    for i, g in enumerate(intent.skill_any_of):
        found = check(f"skill_any_of[{i}]", " or ".join(g.any_of), g.basis, g.relationship)
        if found:
            yield found
    for i, c in enumerate(intent.companies):
        found = check(f"companies[{i}]", c.name, c.basis, c.relationship)
        if found:
            yield found


# ---------------------------------------------------------------------------- proficiency

_DEPTH_CUE = {
    "advanced": re.compile(r"\badvanced\b|\bexpert(?:ise)?\b", I),
    "hands_on": re.compile(r"hands[- ]on", I),
    "working_knowledge": re.compile(r"working knowledge|\bfamiliar(?:ity)?\b", I),
}
_RANK = {"working_knowledge": 1, "hands_on": 2, "advanced": 3}  # mirrors experimental_schema.PROFICIENCY_RANK


def _mentions(skill: str, text: str) -> bool:
    """The text is about this skill: at least half of the skill name's meaningful words appear in it."""
    return bool(stated_evidence(skill, [text], min_share=0.5))


def _unsupported_proficiency(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Iterator[Tuple[str, str, str]]:
    """ERROR when the cited wording, for THIS skill, states no depth or a weaker depth than the one set (an invented or overstated depth).
    Setting a depth BELOW the stated one is not an invented depth; it is reported as the informational `proficiency_understated`."""
    lines = classify_lines(jd) + classify_lines(brief)
    for ref, s in _skill_holders(intent):
        if s.proficiency is None:
            continue
        quote = s.basis.quote if s.basis else None
        texts = ([quote] if quote else []) + [ln["text"] for ln in lines if quote and quote_in(quote, ln["text"])]
        if not quote:
            texts = [ln["text"] for ln in _support(s.name, None, lines)]
        about = [t for t in texts if _mentions(s.name, t)]
        present = {lvl for lvl, rx in _DEPTH_CUE.items() if any(rx.search(t) for t in about)}
        top = max((_RANK[l] for l in present), default=0)
        if _RANK[s.proficiency] > top:
            if present:
                yield ("unsupported_proficiency", ref, f"{s.name!r} is {s.proficiency} but the cited wording about it states only {sorted(present)}: a weaker depth read as {s.proficiency}")
            else:
                yield ("unsupported_proficiency", ref, f"{s.name!r} is {s.proficiency} but the cited source states no depth for it (an unstated depth stays null)")


def understated_proficiency(intent: ExperimentalHiringIntent, jd: str, brief: str) -> List[Dict[str, str]]:
    """Informational only: a depth set below the one the cited wording states (for example `hands_on` for 'Advanced proficiency')."""
    lines = classify_lines(jd) + classify_lines(brief)
    out = []
    for ref, s in _skill_holders(intent):
        quote = s.basis.quote if s.basis else None
        if s.proficiency is None or not quote:
            continue
        texts = [quote] + [ln["text"] for ln in lines if quote_in(quote, ln["text"])]
        present = {lvl for lvl, rx in _DEPTH_CUE.items() if any(rx.search(t) and _mentions(s.name, t) for t in texts)}
        if present and max(_RANK[l] for l in present) > _RANK[s.proficiency]:
            out.append({"code": "proficiency_understated", "ref": ref, "detail": f"{s.name!r} is {s.proficiency} but the wording states {sorted(present)}"})
    return out


# ---------------------------------------------------------------------------- work mode

# "hybrid" is also a word for a mix of strategies or archetypes, so as a WORK MODE it must sit in a line about how / where work is done.
_ARRANGEMENT = re.compile(r"\b(work|working|works|office|basis|schedule|days?|location|arrangement|commut\w*|remote|on-?site|relocat\w*|in-person)\b", I)
_WORK_MODE_CUE = {
    "hybrid": re.compile(r"(?=.*\b(?:work|working|works|office|basis|schedule|days?|location|arrangement|commut\w*|remote|on-?site|relocat\w*|in-person)\b).*\bhybrid\b|\bhybrid\b(?=.*\b(?:work|working|works|office|basis|schedule|days?|location|arrangement|commut\w*|remote|on-?site|relocat\w*|in-person)\b)", I | re.S),
    "onsite": re.compile(r"on[- ]?site|in[- ]office|in[- ]person|office[- ]based|work from (?:the )?office", I),
    "remote": re.compile(r"\bremote(?:ly)?\b|work[- ]from[- ]home|\bwfh\b|telecommut\w*", I),
}


def _work_mode(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Iterator[Tuple[str, str, str]]:
    names = {p.id: _word(p.id) for p in intent.sourcing_paths}
    openers = [_BULLET.sub("", raw).strip() for raw in (jd + "\n" + brief).splitlines()]
    names = {pid: rx for pid, rx in names.items() if any(rx.match(l) for l in openers if l)}
    lines = source_lines(jd, names) + source_lines(brief, names)
    holders = [("location", intent.location, None)] + [(f"paths[{p.id}].location", p.location, p.id) for p in intent.sourcing_paths]
    for ref, loc, scope in holders:
        if loc is None or loc.work_mode is None:
            continue
        hits = [ln for ln in lines if _WORK_MODE_CUE[loc.work_mode].search(ln["text"]) and not ln["negated"]]
        if not hits:
            yield ("work_mode_unsupported", ref, f"work_mode={loc.work_mode!r} but no non-negated source line states it")
            continue
        stated: Set[str] = set().union(*[ln["paths"] for ln in hits if ln["paths"]]) if any(ln["paths"] for ln in hits) else set()
        if scope and scope in names and stated and scope not in stated:
            yield ("work_mode_unsupported", ref, f"work_mode={loc.work_mode!r} for {scope!r} but the sources state it only for {sorted(stated)}")


# ---------------------------------------------------------------------------- entry point


def cross_role_diagnostics(intent: ExperimentalHiringIntent, jd: str, brief: str) -> List[Dict[str, str]]:
    rows = list(iter_atoms(intent))
    found: List[Tuple[str, str, str]] = []
    found += list(_title_analogy(intent, jd, brief))
    found += list(_responsibility_only(intent, jd, brief, rows))
    found += list(_unsupported_current(intent, jd, brief))
    found += list(_unsupported_proficiency(intent, jd, brief))
    found += list(_work_mode(intent, jd, brief))
    return [{"code": c, "ref": r, "detail": d} for c, r, d in found] + understated_proficiency(intent, jd, brief)


def validate_cross_role(intent: ExperimentalHiringIntent, jd: str, brief: str) -> Dict[str, Any]:
    """`validators.validate()` unchanged, plus the five cross-role checks. `errors` merges both; `cross_role_errors` is the new part."""
    report = validate(intent, jd, brief)
    extra = cross_role_diagnostics(intent, jd, brief)
    cross: Dict[str, int] = {}
    for d in extra:
        if d["code"] in CROSS_ROLE_ERROR_CODES:     # informational diagnostics (proficiency_understated) are listed but never counted as errors
            cross[d["code"]] = cross.get(d["code"], 0) + 1
    return {**report, "diagnostics": report["diagnostics"] + extra, "cross_role_errors": cross, "errors": {**report["errors"], **cross}}
