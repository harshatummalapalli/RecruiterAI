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
