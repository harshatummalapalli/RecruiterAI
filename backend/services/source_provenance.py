"""Source classification for the compiler's provenance gate (generic, deterministic, no model, no role-specific rule).

The compiler may emit a provider hard filter only for a value the SOURCE supports (the JD or the recruiter brief) or that approved versioned
knowledge normalizes. Most atoms carry a `basis` (sources + a verbatim quote). A few have no carrier for one (a `role_family` title, a
`CompanyScale`), and any atom may lack one. For those, and to verify a claimed quote, this module answers from the source text itself:

  * `stated(text, sources)`      is the value stated in one sentence of the JD / brief (the same check the intake uses:
                                  `requirement_provenance.stated_evidence`, nearly all meaningful words in ONE sentence)?
  * `classify_title(title, ...)`  TARGET (stated as the role to hire), COMPARISON (every mention is a comparison: "more like", "similar to",
                                  ...), or ABSENT (not stated). A comparison title is never a target title. The cue list is generic English;
                                  nothing here names a role or a title.
  * `number_stated(n, sources)`   is a number (a headcount) stated?
  * `quote_in_sources(quote, ...)` is a claimed quote really in the supplied text?
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from backend.services.requirement_provenance import _meaningful, _sentences, _tokens, stated_evidence


@dataclass(frozen=True)
class SourceTexts:
    """The raw texts an intent was extracted from. Either may be empty (a JD-only role has no brief)."""
    jd: str = ""
    recruiter_brief: str = ""

    def named(self) -> List[Tuple[str, str]]:
        return [(n, t) for n, t in (("jd", self.jd), ("recruiter_brief", self.recruiter_brief)) if t and t.strip()]

    @property
    def present(self) -> bool:
        return bool(self.named())


# A mention preceded, in the same sentence, by one of these is a COMPARISON ("more like a X", "similar to X"), not the role to hire.
_COMPARISON_CUES = re.compile(
    r"\b(?:more\s+like|similar\s+to|resembl(?:es|ing|e)|akin\s+to|comparable\s+to|reminiscent\s+of|"
    r"(?:someone|somebody|anyone|people|person)\s+like|like\s+(?:a|an|the))\b", re.IGNORECASE)

TARGET, COMPARISON, ABSENT = "target", "comparison", "absent"


@dataclass(frozen=True)
class TitleSource:
    state: str                    # target | comparison | absent
    evidence: Optional[str] = None
    source: Optional[str] = None  # jd | recruiter_brief


def _first_word_pos(sentence: str, title: str) -> int:
    words = _meaningful(title)
    low = sentence.lower()
    best = -1
    for w in words[:1] or _tokens(title)[:1]:
        best = low.find(w[: max(4, len(w) - 1)])
    return best


def classify_title(title: str, sources: SourceTexts) -> TitleSource:
    """TARGET if any sentence that states the title does not introduce it with a comparison cue; COMPARISON if every stating sentence does."""
    comparison: Optional[TitleSource] = None
    for name, text in sources.named():
        for sentence in _sentences(text):
            if not stated_evidence(title, [sentence]):
                continue
            pos = _first_word_pos(sentence, title)
            cue = next((m for m in _COMPARISON_CUES.finditer(sentence) if pos < 0 or m.end() <= pos + 1), None)
            if cue is None:
                return TitleSource(TARGET, sentence[:220], name)
            comparison = comparison or TitleSource(COMPARISON, sentence[:220], name)
    return comparison or TitleSource(ABSENT)


def stated(text: str, sources: SourceTexts) -> Optional[Tuple[str, str]]:
    """(source name, sentence) that states `text`, else None."""
    for name, body in sources.named():
        ev = stated_evidence(text, _sentences(body))
        if ev:
            return name, ev
    return None


def sentences_about(label: str, sources: SourceTexts) -> List[str]:
    """Every source sentence that states `label` (the intake's one-sentence check)."""
    out: List[str] = []
    for _name, body in sources.named():
        for sentence in _sentences(body):
            if stated_evidence(label, [sentence]):
                out.append(sentence)
    return out


def number_stated(n: int, sources: SourceTexts) -> Optional[Tuple[str, str]]:
    needle = re.compile(rf"(?<![\d.]){n}(?![\d])|(?<![\d.]){n // 1000}\s*k\b" if n >= 1000 else rf"(?<![\d.]){n}(?![\d])", re.IGNORECASE)
    for name, body in sources.named():
        cleaned = re.sub(r"(?<=\d),(?=\d{3})", "", body)
        for sentence in _sentences(cleaned):
            if needle.search(sentence):
                return name, sentence[:220]
    return None


def _squash(s: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s.casefold()).split())


def quote_in_sources(quote: str, sources: SourceTexts) -> Optional[str]:
    """The source that contains this quote (punctuation- and case-insensitive), else None."""
    q = _squash(quote)
    if not q:
        return None
    for name, body in sources.named():
        if q in _squash(body):
            return name
    return None


# ======================================================================================================================
# SEMANTIC provenance: a qualifier of a constraint (its temporal scope, its requiredness, a depth, an accepted alternative level, a leadership kind,
# a distance, a work arrangement, a number) needs the same source support as the value. Generic, lexical, role-agnostic.
# ======================================================================================================================

_I = re.IGNORECASE
_CURRENT_CUE = re.compile(r"(?<!stay )(?<!keep )(?<!remain )\b(currently|current|presently|at present|right now|now|present (?:role|position|employer|company|job))\b", _I)
_PAST_CUE = re.compile(r"\b(previous(?:ly)?|prior|formerly|earlier|past|used to|before|has worked|have worked|had worked|worked (?:on|with|in|at|extensively)|former)\b", _I)
_PREFERENCE_CUE = re.compile(
    r"\b(preferred|preferably|prefer|nice[- ]to[- ]have|ideal(?:ly)?|bonus|a plus|is a plus|plus point|desirable|desired|good to have|optional|advantage|an asset|would be (?:an? )?(?:plus|advantage|asset|helpful))\b", _I)
_DEPTH_CUE = {
    "advanced": re.compile(r"\badvanced\b|\bexpert(?:ise)?\b", _I),
    "hands_on": re.compile(r"hands[- ]on", _I),
    "working_knowledge": re.compile(r"working knowledge|\bfamiliar(?:ity)?\b", _I),
}
_DEPTH_RANK = {"working_knowledge": 1, "hands_on": 2, "advanced": 3}
_LEADERSHIP_CUE = {
    "people": re.compile(r"\bpeople\b|\bteams?\b|\bmanag\w+|\bmentor\w*|\bcoach\w*|\bdirect reports?\b|\bleading\b", _I),
    "technical": re.compile(r"\btechnical\b|\btechnology\b|\barchitect\w*|\btech lead\b|\bengineering lead\b", _I),
}
_MODE_CUE = {
    "hybrid": re.compile(r"\bhybrid\b", _I),
    "onsite": re.compile(r"on[- ]?site|in[- ]office|in[- ]person|office[- ]based|work from (?:the )?office", _I),
    "remote": re.compile(r"\bremote(?:ly)?\b|work[- ]from[- ]home|\bwfh\b|telecommut\w*", _I),
}
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}


def clauses(text: str) -> List[str]:
    return [c.strip() for c in re.split(r"[;\n]|(?<=[.!?])\s+", text or "") if c and c.strip()]


def focus(label: str, text: str) -> str:
    """The part of the source text that is about `label` (its clauses), else the whole text."""
    about = [c for c in clauses(text) if stated_evidence(label, [c], min_share=0.5)]
    return " ".join(about) if about else (text or "")


def temporal_supported(relationship: Optional[str], text: str) -> bool:
    """`current` needs a present-use cue, `past` a past-use cue in the text about the value. `any` / unspecified make no temporal claim."""
    if relationship == "current":
        return bool(_CURRENT_CUE.search(text or ""))
    if relationship == "past":
        return bool(_PAST_CUE.search(text or ""))
    return True


def requiredness_supported(strength: Optional[str], text: str) -> bool:
    """`required` is unsupported when the text about the value says it is only preferred / a plus. (A requirement the source states plainly carries no cue.)"""
    if strength == "required":
        return not _PREFERENCE_CUE.search(text or "")
    return True


def depth_supported(level: str, text: str) -> bool:
    """A depth is supported only by a cue of that level (a weaker statement is not read as a stronger depth)."""
    cues = {lvl for lvl, rx in _DEPTH_CUE.items() if rx.search(text or "")}
    return bool(cues) and max(_DEPTH_RANK[c] for c in cues) >= _DEPTH_RANK.get(level, 99)


def level_stated(level: str, text: str) -> bool:
    return bool(level and _squash(level) and re.search(rf"\b{re.escape(_squash(level))}\b", _squash(text or "")))


def leadership_stated(kind: str, text: str) -> bool:
    rx = _LEADERSHIP_CUE.get(kind)
    return bool(rx and rx.search(text or ""))


def mode_stated(mode: str, text: str) -> bool:
    rx = _MODE_CUE.get(mode)
    return bool(rx and rx.search(text or ""))


def number_in_text(n: int, text: str) -> bool:
    cleaned = re.sub(r"(?<=\d),(?=\d{3})", "", text or "")
    if re.search(rf"(?<![\d.]){n}(?!\d)", cleaned):
        return True
    return any(v == n and re.search(rf"\b{w}\b", cleaned, _I) for w, v in _NUMBER_WORDS.items())
