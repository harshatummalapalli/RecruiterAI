"""Builds a CandidateEvidence from a raw Candidate + the SearchIntent that
surfaced it. This is the ONE place role-alignment evidence gets computed —
CandidateRanker and MatchExplainer both call this instead of each deriving
their own (partial, disagreeing) view of the candidate, which is what caused
the original inconsistency between backend ranking and the frontend's
independent scoring.

Generalization rule (hard requirement): nothing in this file may hardcode a
role-specific keyword list (e.g. "data engineer" -> [...]). All role
alignment is derived from the SearchIntent passed in — the role's own title,
seniority, and Core/Supporting/Differentiator signal sentences from the
Confirmed Hiring Intent that produced this exact search. The same function
evaluates a Backend Engineer search and a Lead Data Analyst search identically.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import (
    CandidateEvidence,
    ContactEvidence,
    EducationEntry,
    HarvestEvidence,
    MatchedSignal,
    PastRole,
    RoleAlignment,
    SearchEvidence,
    TextSource,
    UncertaintyNote,
)
from backend.models.search_intent import SearchIntent

# A conservative, generic (not role-specific) pattern for a self-reported
# total-years claim in a candidate's own "about" text (e.g. "11+ years",
# "8 years"). Used only to label such a claim explicitly as self-reported —
# never to populate, compute, or stand in for a verified years-of-experience
# field. See apply_harvest_evidence.
_SELF_REPORTED_YEARS_RE = re.compile(r"\b(\d{1,2}\+?)\s*years?\b", re.IGNORECASE)

# Pure grammatical connectors/seniority words stripped before comparing
# titles or extracting signal terms — never a domain/technology term, and
# never role-specific (a "data" or "backend" or "security" term is always
# kept, whatever the role).
_STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "for", "with", "in", "on", "to", "is", "are",
    "senior", "junior", "lead", "principal", "staff", "sr", "jr", "i", "ii", "iii",
    "engineer", "engineering",  # generic role suffix, kept out of TERM extraction only
}
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")

# Generic engineering nouns that restate the domain rather than identify a
# specific, checkable piece of evidence — "data" or "cloud" appearing in a
# differentiator sentence about a data-engineering role would otherwise
# "match" almost every candidate's title trivially, which is not real
# differentiating evidence. This list is broad-domain-agnostic (not tied to
# any one role family) and only suppresses weak, near-universal terms from
# being counted as a signal hit; it never blocks a specific technology name.
#
# PASS 4 (evidence quality): this stoplist is a SECONDARY aid, not the
# primary fix for weak evidence — see _extract_signal_terms below, which
# requires multi-word phrase context for most words. These entries are
# words with essentially no standalone domain meaning in ANY phrase (a
# temporal/business-generic connector, not a concept a candidate could
# "demonstrate") — real PASS 3 regressions ("prior", "using", "decisions")
# plus the same already-stopworded "engineer"/"engineering" family.
_GENERIC_TERMS = {
    "data", "cloud", "production", "system", "systems", "service", "services",
    "platform", "platforms", "technology", "technologies", "experience",
    "architecture", "architectures", "engineering", "development", "software",
    "infrastructure", "tools", "tooling", "frameworks", "framework", "solutions",
    "operating", "operations", "environments", "environment", "management",
    # Added after auditing real search results: these are common words in
    # CrustData's own INDUSTRY classification strings (e.g. "Technology,
    # Information and Internet"), which are corporate taxonomy tags, not a
    # description of a candidate's actual skills — "information" matched
    # from a past employer's industry tag was flagged as false evidence of
    # "information retrieval" expertise, which it was not.
    "information", "internet", "consulting", "network", "networking",
    "digital", "computing", "enterprise", "product", "products", "business",
    # PASS 4 regression fixes (PART 10 tests 3, 5, 6): pure connectors, never
    # a checkable concept on their own or as part of a phrase.
    "prior", "using", "use", "used", "decisions", "decision",
    # Plural sibling of the "engineer"/"engineering" stopwords above, which
    # were already excluded from title comparison but not from signal-term
    # extraction — closing that gap.
    "engineers",
}

# PASS 4 (evidence quality, PART 4/9): words that ARE real, checkable
# concepts when they anchor a multi-word phrase a candidate could plausibly
# demonstrate ("A/B testing", "technical leadership", "distributed systems
# work") but carry no standalone meaning at all ("work described there
# includes 'work'") — the exact PASS 3 regression. Unlike _GENERIC_TERMS,
# these are never dropped from the candidate token stream entirely; they
# just can never be the LONE word in a matched phrase — see
# _extract_signal_terms's run-grouping below, which is what makes this rule
# generalize (any word here becomes usable evidence again the moment the JD
# sentence gives it a neighboring content word), rather than a role-specific
# rule or a wholesale ban.
_PHRASE_ONLY_TERMS = {"work", "working", "worked", "technical", "testing", "tested", "consumer", "consumers"}


def _words(text: Optional[str]) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _significant_words(text: Optional[str], min_len: int = 3) -> List[str]:
    return [w for w in _words(text) if len(w) >= min_len and w not in _STOPWORDS]


def _is_technical_token(original_token: str, *, sentence_initial: bool = False) -> bool:
    """A capitalized proper-noun/acronym ("RAG", "Kafka", "Solr", "SaaS") or
    a token carrying digits/symbols ("k8s", "c++", "c#") — the same class of
    token the old capitalized-phrase regex looked for, but evaluated
    per-token so it can participate in phrase-run grouping below. These are
    specific and checkable enough to stand alone even at 1-2 characters, and
    are exempt from the phrase-only restriction: a real technology name is
    never "noise" merely for appearing without a neighbor.

    `sentence_initial` must be set for the sentence's first token — ordinary
    English capitalizes the first word of a sentence regardless of what it
    is ("Testing skills required."), so capitalization alone is not a
    proper-noun signal there; only a digit/symbol still counts."""
    if not sentence_initial and len(original_token) >= 2 and original_token[0].isupper():
        return True
    return any(ch.isdigit() or ch in "+#" for ch in original_token)


@dataclass
class _SignalTerm:
    """One candidate term extracted from a Core/Supporting/Differentiator
    sentence — either a single distinctive word or a multi-word phrase run
    (see _extract_signal_terms). `is_phrase` controls how matching is
    performed: a phrase requires its words to co-occur in order within a
    small window of the candidate's own text (real context), never a bare
    substring check."""

    words: List[str]
    is_phrase: bool

    @property
    def key(self) -> str:
        return " ".join(self.words)


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.\-]*")


def _merge_slash_tokens(tokens: List[str], spans: List[Tuple[int, int]], sentence: str) -> Tuple[List[str], List[Tuple[int, int]]]:
    """PASS 5 (PART 5): '/' isn't in `_TOKEN_RE`'s character class, so
    "A/B testing" tokenizes as the two near-useless single-character tokens
    "A"/"B" plus "testing" — leaving "testing" (a phrase-only term) with no
    significant neighbor to be rescued by, so a real "A/B testing"
    requirement silently produced zero evidence. This merges any run of
    tokens joined by a bare '/' (no surrounding space) back into one token
    — "A/B", "C/C++" — right after tokenization, before significance is
    ever evaluated. Smallest targeted fix: it touches only slash-joined
    runs, not the tokenizer's character class itself. "C#" and ".NET"
    already tokenize safely today ("C#" is one token since '#' is a
    continuation character; ".NET" becomes "NET", which still matches
    "...\\.NET..." via the existing word-boundary check since '.' isn't a
    word character) and need no change here."""
    merged_tokens: List[str] = []
    merged_spans: List[Tuple[int, int]] = []
    i = 0
    while i < len(tokens):
        j = i
        while j + 1 < len(tokens) and sentence[spans[j][1] : spans[j + 1][0]] == "/":
            j += 1
        merged_tokens.append(sentence[spans[i][0] : spans[j][1]])
        merged_spans.append((spans[i][0], spans[j][1]))
        i = j + 1
    return merged_tokens, merged_spans


def _extract_signal_terms(sentence: str) -> List[_SignalTerm]:
    """Literal candidate terms to look for from one Core/Supporting/
    Differentiator sentence.

    PASS 4 (evidence quality): the unit of extraction is no longer "every
    individual significant word" — it's a PHRASE: a contiguous run of
    significant words in the ORIGINAL sentence, tolerating at most one
    intervening filler word (a stopword, a generic term, or a short word) so
    that "data-driven performance work" is extracted and matched as ONE
    three-word phrase, not three independent single-word terms. This is
    what turns "work described there includes 'work'" into a rejected
    match: nothing in a candidate's text says "data-driven performance
    work" together, only the bare word "work" — which the phrase mechanism
    never tests in isolation once it has a phrase-mate in the JD sentence.

    A run of length 1 (no neighboring significant word in the JD sentence at
    all) is still accepted as a standalone term UNLESS the word is in
    `_PHRASE_ONLY_TERMS` and isn't a distinctive technical token — this is
    what keeps genuinely single-concept evidence like "distributed",
    "orchestration", "analytics", or "Kafka" working exactly as before,
    while "testing"/"technical"/"work"/"consumer" only count when the JD
    sentence itself gives them real phrase context.

    Generic text extraction throughout — nothing here is a role-specific
    dictionary."""
    sentence = sentence or ""
    raw_matches = list(_TOKEN_RE.finditer(sentence))
    raw_tokens = [m.group(0) for m in raw_matches]
    raw_spans = [m.span() for m in raw_matches]
    tokens, spans = _merge_slash_tokens(raw_tokens, raw_spans, sentence)
    # Trailing '.' stripped per token (sentence-ending punctuation, not part
    # of the term — "Kafka." at the end of a sentence must match "Kafka");
    # an internal '.' ("Node.js") is preserved since rstrip only trims the end.
    tokens = [t.rstrip(".") for t in tokens]
    keep = [bool(t) for t in tokens]
    tokens = [t for t, k in zip(tokens, keep) if k]
    spans = [s for s, k in zip(spans, keep) if k]

    significant: List[bool] = []
    proper: List[bool] = []
    phrase_only: List[bool] = []
    for i, tok in enumerate(tokens):
        lower = tok.lower()
        is_proper = _is_technical_token(tok, sentence_initial=(i == 0))
        is_sig = lower not in _STOPWORDS and lower not in _GENERIC_TERMS and (len(lower) >= 4 or is_proper)
        significant.append(is_sig)
        proper.append(is_proper)
        phrase_only.append(is_sig and lower in _PHRASE_ONLY_TERMS and not is_proper)

    terms: List[_SignalTerm] = []
    seen_keys: set = set()

    def _add(term: _SignalTerm) -> None:
        if term.key not in seen_keys:
            seen_keys.add(term.key)
            terms.append(term)

    # Every ORDINARY significant word (not phrase-only) stands on its own,
    # exactly as before PASS 4 — this is what keeps single-concept evidence
    # like "distributed", "orchestration", "analytics", "stakeholder", or
    # "Kafka" working unchanged: nothing about being grammatically near an
    # unrelated JD word (e.g. "SQL" near "analytics" in "data to inform
    # decisions (SQL or analytics tooling)") should ever suppress a term
    # that is perfectly fine standing alone.
    for i, tok in enumerate(tokens):
        if significant[i] and not phrase_only[i]:
            _add(_SignalTerm(words=[tok.lower()], is_phrase=False))

    # Phrase-only words ("work", "testing", "technical", "consumer" — see
    # _PHRASE_ONLY_TERMS) are the narrow exception: they never stand alone,
    # only as part of a real contiguous run alongside another significant
    # word in the SAME JD sentence — this is the actual fix for "work
    # described there includes 'work'". A comma/semicolon/colon between two
    # words is a hard break even within the gap tolerance below, since a JD
    # sentence is frequently a comma-separated LIST of distinct concepts
    # ("instrumentation, on-call, incident response, and data-driven
    # performance work") — each list item gets its own run, not one
    # unrealistic whole-list phrase.
    runs: List[List[int]] = []
    current: List[int] = []
    gap = 0
    prev_end: Optional[int] = None
    for i, is_sig in enumerate(significant):
        hard_break = False
        if prev_end is not None:
            between = sentence[prev_end : spans[i][0]]
            hard_break = any(ch in between for ch in ",;:")
        if is_sig:
            if current and (gap > 1 or hard_break):
                runs.append(current)
                current = []
            current.append(i)
            gap = 0
            prev_end = spans[i][1]
        else:
            gap += 1
    if current:
        runs.append(current)

    for run in runs:
        if len(run) < 2 or not any(phrase_only[i] for i in run):
            continue  # no phrase-only member to rescue — already handled above (or correctly discarded if len==1 and phrase-only)
        words = [tokens[i].lower() for i in run]
        _add(_SignalTerm(words=words, is_phrase=True))
    # Phrases first: when a source contains both a richer phrase match and a
    # looser single-word match for the same sentence, prefer the phrase.
    terms.sort(key=lambda t: (not t.is_phrase, t.key))
    return terms


_BOUNDARY_BEFORE = r"(?<![A-Za-z0-9])"
_BOUNDARY_AFTER = r"(?![A-Za-z0-9])"
# Up to 3 filler words tolerated between consecutive words of a matched
# phrase — real context ("Led A/B testing framework for product
# experimentation") without demanding the JD's exact wording verbatim.
_PHRASE_GAP = r"(?:[A-Za-z0-9+#.\-]+\W+){0,3}"


def _compile_term_pattern(term: _SignalTerm) -> "re.Pattern[str]":
    if not term.is_phrase:
        return re.compile(_BOUNDARY_BEFORE + re.escape(term.words[0]) + _BOUNDARY_AFTER, re.IGNORECASE)
    pattern = _BOUNDARY_BEFORE + re.escape(term.words[0]) + _BOUNDARY_AFTER
    for word in term.words[1:]:
        pattern += r"\W+" + _PHRASE_GAP + _BOUNDARY_BEFORE + re.escape(word) + _BOUNDARY_AFTER
    return re.compile(pattern, re.IGNORECASE)


def _extract_context_sentence(text: str, match: "re.Match[str]") -> str:
    """The sentence the match was actually found in, not the whole
    (possibly paragraph-length) source text — "Led A/B testing framework
    for product experimentation across multiple SaaS products.", not a full
    employment description dumped verbatim. For short sources (a title, a
    headline, a certification title) this naturally returns the whole
    string, since there's no sentence punctuation to split on."""
    start, end = match.span()
    boundary_starts = [text.rfind(ch, 0, start) for ch in ".!?\n"]
    sentence_start = max(boundary_starts) + 1 if max(boundary_starts) != -1 else 0
    boundary_ends = [text.find(ch, end) for ch in ".!?\n"]
    boundary_ends = [b for b in boundary_ends if b != -1]
    sentence_end = min(boundary_ends) + 1 if boundary_ends else len(text)
    snippet = text[sentence_start:sentence_end].strip()
    return snippet or text.strip()


def _format_terms(terms: Any) -> str:
    """Recruiter-readable term list: “backend”, “engineer” — never a Python
    list repr like ['backend'] leaking into a sentence."""
    return ", ".join(f"“{term}”" for term in sorted(terms))


def _classify_title_relevance(
    candidate_title: str, headline: str, target_title: Optional[str], include_titles: List[str]
) -> Tuple[str, str]:
    candidate_norm = (candidate_title or "").strip().lower()
    if not candidate_norm:
        return "unclear", "Candidate has no current title on record."

    if target_title and candidate_norm == target_title.strip().lower():
        return "direct", f"Current title matches the target title \"{target_title}\" exactly."

    expanded_family = {t.strip().lower() for t in include_titles if t}
    if candidate_norm in expanded_family:
        return "direct", f"Current title \"{candidate_title}\" is a known equivalent of the target role."

    # min_len=2 here (vs. the default 3 used for signal-term extraction):
    # job titles are short, curated text where a 2-letter token is almost
    # always a meaningful acronym ("AI", "ML", "QA", "UX") rather than noise
    # — dropping them caused "Senior AI Engineer" vs. "Senior AI Platform
    # Engineer" to show zero overlap despite sharing the role's own core
    # term. Caught by testing this exact model against real candidates.
    #
    # The formal title field is sometimes a generic internal label (e.g.
    # "Senior Software Engineer") while the candidate's own headline
    # self-describes the actual work far more specifically ("Senior AI
    # Engineer | LLM Apps, RAG & Agentic Workflows"). Both are real,
    # provider-returned candidate text, so this checks title+headline
    # together rather than the formal title field alone — also found to
    # matter on the same real search.
    target_words = set(_significant_words(target_title, min_len=2))
    candidate_title_words = set(_significant_words(candidate_title, min_len=2))
    combined_words = candidate_title_words | set(_significant_words(headline, min_len=2))
    if target_words and combined_words:
        overlap = target_words & combined_words
        ratio = len(overlap) / len(target_words)
        source = "title" if overlap <= candidate_title_words else "title/headline"
        shared = _format_terms(overlap)
        if ratio >= 0.6:
            return "direct", f"Current {source} shares the core term(s) {shared} with the target role."
        if ratio > 0:
            return "adjacent", f"Current {source} shares the term(s) {shared} with the target role, but not all of it."

    return "unclear", "Current title/headline has no clear textual overlap with the target role; not verified either way."


def _classify_seniority(
    evidence: CandidateEvidence, target_seniority: Optional[str], minimum_years: Optional[int] = None
) -> Tuple[Optional[bool], str]:
    """Evidence-based, not provider-normalized-field-based. A real live
    candidate exposed the bug this fixes: CrustData's own `seniority_level`
    said "Senior" while the candidate's actual current title was "Team Lead
    | Cyber Incident Response" against a "Lead" target — a false concern,
    because the provider-normalized field was trusted as ground truth
    instead of as one signal among several. `candidate.seniority_level` is a
    SIGNAL, not TRUTH.

    Evidence hierarchy, checked in order — the first one that actually says
    something about the target seniority wins:
    1. Current title (does it literally name the target seniority?)
    2. The two most recent past-role titles (career trajectory)
    3. Provider-normalized seniority field (last resort — no title evidence
       either confirmed or contradicted the target)."""
    if not target_seniority:
        return None, "No target seniority was specified for this search."
    target_norm = target_seniority.strip().lower()
    if not target_norm:
        return None, "No target seniority was specified for this search."

    title_sources: List[Tuple[str, Optional[str]]] = [("current title", evidence.current_title)]
    for role in evidence.past_roles[:2]:
        title_sources.append((f"recent past role (\"{role.title}\")" if role.title else "recent past role", role.title))

    for label, text in title_sources:
        if not text:
            continue
        if target_norm in text.strip().lower():
            return True, f"Candidate's {label} directly names the target seniority (\"{target_seniority}\")."

    # Step 3 (replaces trusting the provider's label first): when the search
    # states a minimum-years requirement and the candidate's role dates let
    # us derive their time in work, compare those two FACTS. A provider label
    # like "Entry Level" on someone with several years of dated roles was
    # found to produce false level concerns on a real search.
    if minimum_years and evidence.derived_experience_years is not None:
        years = evidence.derived_experience_years
        if years >= minimum_years:
            return True, (
                f"About {years:g} years of professional experience are visible in dated roles, which meets the "
                f"{minimum_years}+ years asked for a {target_seniority} role; years in the specific discipline "
                "are not independently verified."
            )
        return False, (
            f"About {years:g} years of professional experience are visible in dated roles, below the "
            f"{minimum_years}+ years asked for a {target_seniority} role."
        )

    candidate_seniority = evidence.current_seniority
    if not candidate_seniority:
        return (
            None,
            "The candidate's seniority level is not stated on their profile, and no title evidence "
            "(current or recent past roles) confirms or contradicts the target seniority.",
        )
    candidate_norm = candidate_seniority.strip().lower()
    if candidate_norm == target_norm or candidate_norm in target_norm or target_norm in candidate_norm:
        return True, f"Candidate's seniority level (\"{candidate_seniority}\") aligns with the target (\"{target_seniority}\")."
    return False, (
        f"Candidate's seniority level (\"{candidate_seniority}\") does not match the target (\"{target_seniority}\"), "
        "and no title evidence (current or recent past roles) directly names the target seniority either."
    )


# Seniority ladder used ONLY to compare a stated level in a title with the
# target level. A title with no marker on this ladder ("Backend Engineer")
# states no level, and years alone are never used to place someone on it.
_LEVEL_LADDER: Tuple[Tuple[int, str, Tuple[str, ...]], ...] = (
    (0, "intern", ("intern", "internship", "trainee", "apprentice")),
    (1, "junior", ("junior", "jr", "entry", "graduate")),
    (2, "mid", ("mid", "intermediate")),
    (3, "senior", ("senior", "sr")),
    (4, "staff/lead", ("staff", "lead")),
    (5, "principal", ("principal", "distinguished", "fellow")),
    (6, "director", ("director", "vp", "vice", "head", "chief", "cto")),
)
_NUMBERED_LEVEL = re.compile(r"\b(?:level|engineer|developer|sde|swe|analyst)\s+(iii|ii|i|3|2|1)\b", re.IGNORECASE)
_NUMBERED_RANK = {"i": 1, "1": 1, "ii": 2, "2": 2, "iii": 3, "3": 3}


def _level_marker(text: Optional[str]) -> Optional[Tuple[int, str]]:
    """The highest level a title/headline states, as (rank, label), or None
    when it states none."""
    if not text:
        return None
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    found: List[int] = []
    for rank, _label, words in _LEVEL_LADDER:
        if any(word in tokens for word in words):
            found.append(rank)
    numbered = _NUMBERED_LEVEL.search(text)
    if numbered:
        found.append(_NUMBERED_RANK[numbered.group(1).lower()])
    if not found:
        return None
    rank = max(found)
    return rank, next(label for r, label, _ in _LEVEL_LADDER if r == rank)


def _classify_experience_floor(
    evidence: CandidateEvidence, minimum_years: Optional[int]
) -> Tuple[Optional[bool], str]:
    """The arithmetic fact only: do the dated roles add up to the years the
    search asked for. None when the search asked for no minimum or the
    profile has no usable dates."""
    if not minimum_years:
        return None, ""
    years = evidence.derived_experience_years
    if years is None:
        return None, f"No dated roles on the profile, so the {minimum_years}+ years asked cannot be checked."
    if years >= minimum_years:
        return True, (
            f"About {years:g} years of professional experience are visible in dated roles, which meets the "
            f"{minimum_years}+ years asked; years in the specific discipline are not independently verified."
        )
    return False, (
        f"About {years:g} years of professional experience are visible in dated roles, below the "
        f"{minimum_years}+ years asked."
    )


def _classify_level(
    evidence: CandidateEvidence, target_seniority: Optional[str], floor: Optional[bool]
) -> Tuple[Optional[str], str]:
    """Does the candidate's own stated level fit the target, judged from the
    titles and never from years alone.

    Evidence, strongest first: the current title, then the headline, then the
    two most recent earlier titles. Earlier titles can only CONFIRM a fit
    (someone whose current title states no level but was recently a Senior
    Engineer) - they never flag a candidate as above or below, because titles
    drift. Where the current title and the headline point different ways the
    answer is "unclear". A title that states no level places nobody on the
    ladder: the answer is "unclear", except that a profile whose dated roles
    fall short of the years the search asked for is "below". "above" and
    "below" describe what the profile may indicate, not a verdict."""
    target = _level_marker(target_seniority)
    if not target_seniority or target is None:
        return None, ""
    target_rank, _ = target

    def relation(rank: int) -> str:
        return "above" if rank > target_rank else "below" if rank < target_rank else "aligned"

    title = _level_marker(evidence.current_title)
    headline = _level_marker(evidence.headline)
    title_text = evidence.current_title or ""

    if title and headline and relation(title[0]) != relation(headline[0]):
        return "unclear", (
            f"The current title (\"{title_text}\", {title[1]}-level) and the headline ({headline[1]}-level) point to different "
            f"levels, so fit with the target {target_seniority} role cannot be confirmed from the profile."
        )

    stated = title or headline
    if stated:
        where = f"current title (\"{title_text}\")" if title else "headline"
        fit = relation(stated[0])
        if fit == "aligned":
            return fit, f"The {where} reads as {stated[1]}-level, consistent with the target {target_seniority} role."
        if fit == "above":
            return fit, f"The {where} reads as {stated[1]}-level, which may indicate a level above the target {target_seniority} role."
        return fit, f"The {where} reads as {stated[1]}-level, which may indicate a level below the target {target_seniority} role."

    for role in evidence.past_roles[:2]:
        earlier = _level_marker(role.title)
        if earlier and relation(earlier[0]) == "aligned":
            return "aligned", (
                f"The current title states no level, but a recent earlier role (\"{role.title}\") read as {earlier[1]}-level, "
                f"consistent with the target {target_seniority} role."
            )

    if floor is False:
        return "below", (
            f"The current title states no level, and the dated roles fall short of the years asked for the target "
            f"{target_seniority} role."
        )
    return "unclear", (
        f"The current title states no level, so fit with the target {target_seniority} role cannot be confirmed "
        "from the profile."
    )


def _parse_role_date(value: Any) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _derive_experience_years(
    current: Dict[str, Any], past_roles: List[PastRole], today: Optional[date] = None
) -> Optional[float]:
    """Time covered by the employment dates on record, in years, with
    overlapping roles merged so concurrent jobs aren't double counted. A
    current role runs to today; a past role with no end date is skipped
    rather than guessed. Derived from CrustData's own dated roles — a fact
    we can show, not the candidate's claim and not a provider field."""
    today = today or date.today()
    intervals: List[Tuple[date, date]] = []
    current_start = _parse_role_date(current.get("start_date")) if current else None
    if current_start and current_start <= today:
        intervals.append((current_start, today))
    for role in past_roles:
        start, end = _parse_role_date(role.start_date), _parse_role_date(role.end_date)
        if start and end and start <= end:
            intervals.append((start, end))
    if not intervals:
        return None
    intervals.sort()
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    days = sum((end - start).days for start, end in merged)
    return round(days / 365.25, 1)


def _alignment_from_judgments(
    evidence: CandidateEvidence,
    intent: SearchIntent,
    title_relevance: str,
    title_basis: str,
    seniority_alignment: Optional[bool],
    seniority_basis: str,
    level_kwargs: Dict[str, Any],
) -> RoleAlignment:
    """Role alignment built ONLY from judgments whose quote was verified
    against the profile text (see requirement_judge.py). A requirement with
    no verified judgment is unmatched — never a guessed match."""
    by_key = {(j.get("tier"), j.get("signal_text")): j for j in (evidence.requirement_judgments or [])}
    matched: List[MatchedSignal] = []
    unmatched: List[MatchedSignal] = []
    for tier, sentences in (
        ("core", intent.core_signals),
        ("supporting", intent.supporting_signals),
        ("differentiator", intent.differentiator_signals),
    ):
        for sentence in sentences:
            judgment = by_key.get((tier, sentence))
            if judgment and judgment.get("verdict") == "met":
                matched.append(
                    MatchedSignal(
                        tier=tier,
                        signal_text=sentence,
                        matched_term=judgment.get("term") or "",
                        source=judgment.get("source") or "",
                        evidence_detail=judgment.get("evidence_detail") or "",
                        evidence_type=judgment.get("evidence_type") or "",
                        evidence_text=judgment.get("quote") or "",
                        strength=judgment.get("strength") or "",
                    )
                )
            else:
                unmatched.append(MatchedSignal(tier=tier, signal_text=sentence, matched_term="", source=""))
    return RoleAlignment(
        title_relevance=title_relevance,
        title_relevance_basis=title_basis,
        seniority_alignment=seniority_alignment,
        seniority_alignment_basis=seniority_basis,
        matched_signals=matched,
        unmatched_signals=unmatched,
        **level_kwargs,
    )


def _build_role_alignment(evidence: CandidateEvidence, intent: SearchIntent) -> RoleAlignment:
    title_relevance, title_basis = _classify_title_relevance(
        evidence.current_title, evidence.headline, intent.role.title, intent.titles.include_titles
    )
    minimum_years = intent.experience.minimum_years or None
    seniority_alignment, seniority_basis = _classify_seniority(evidence, intent.role.seniority, minimum_years)
    floor, floor_basis = _classify_experience_floor(evidence, minimum_years)
    level_fit, level_basis = _classify_level(evidence, intent.role.seniority, floor)
    level_kwargs = dict(
        experience_floor=floor, experience_floor_basis=floor_basis, level_fit=level_fit, level_basis=level_basis
    )

    if evidence.requirement_judgments is not None:
        return _alignment_from_judgments(
            evidence, intent, title_relevance, title_basis, seniority_alignment, seniority_basis, level_kwargs
        )

    # Sources are searched in STRENGTH order (demonstrated work/certification
    # before headline/title-history/named-skill — see TextSource docs on
    # labeled_text_sources), so that when a term is corroborated in more
    # than one place, the resulting single MatchedSignal is attributed to —
    # and worded from — the strongest one (PASS 4 / PART 7), not merely
    # whichever source happened to be checked first.
    sources = evidence.labeled_text_sources()
    matched: List[MatchedSignal] = []
    seen_matches: set = set()  # (tier, term.key) — avoid duplicate bullets for the same corroborated concept
    unmatched: List[MatchedSignal] = []
    tiered_signals = [
        ("core", intent.core_signals),
        ("supporting", intent.supporting_signals),
        ("differentiator", intent.differentiator_signals),
    ]
    for tier, sentences in tiered_signals:
        for sentence in sentences:
            terms = _extract_signal_terms(sentence)
            patterns = [(term, _compile_term_pattern(term)) for term in terms]
            found_source: Optional[TextSource] = None
            found_term: Optional[_SignalTerm] = None
            found_match: Optional["re.Match[str]"] = None
            for source in sources:
                for term, pattern in patterns:
                    match = pattern.search(source.text or "")
                    if match:
                        found_source, found_term, found_match = source, term, match
                        break
                if found_term:
                    break
            if found_term and (tier, found_term.key) not in seen_matches:
                seen_matches.add((tier, found_term.key))
                context = _extract_context_sentence(found_source.text or "", found_match) if found_match else ""
                matched.append(
                    MatchedSignal(
                        tier=tier,
                        signal_text=sentence,
                        matched_term=found_term.key,
                        source=found_source.label,
                        evidence_detail=found_source.detail,
                        evidence_type=found_source.evidence_type,
                        evidence_text=context,
                        strength=found_source.strength,
                    )
                )
            elif not found_term:
                unmatched.append(MatchedSignal(tier=tier, signal_text=sentence, matched_term="", source=""))

    return RoleAlignment(
        title_relevance=title_relevance,
        title_relevance_basis=title_basis,
        seniority_alignment=seniority_alignment,
        seniority_alignment_basis=seniority_basis,
        matched_signals=matched,
        unmatched_signals=unmatched,
        **level_kwargs,
    )


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_past_roles(past_list: Any) -> List[PastRole]:
    roles: List[PastRole] = []
    for entry in past_list or []:
        if not isinstance(entry, dict):
            continue
        roles.append(
            PastRole(
                title=entry.get("title") or "",
                company=entry.get("name") or entry.get("company_name") or "",
                industries=[i for i in (entry.get("company_industries") or []) if isinstance(i, str)],
                function=entry.get("function_category"),
                seniority=entry.get("seniority_level"),
                start_date=entry.get("start_date"),
                end_date=entry.get("end_date"),
                description=entry.get("description"),
            )
        )
    return roles


def _clean(value: Any) -> Optional[str]:
    """Empty strings are a real, observed shape in CrustData's education
    response (e.g. description: "") — treated as absent, not as an empty
    but present fact."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _parse_education(raw: Dict[str, Any]) -> List[EducationEntry]:
    education = _coerce_mapping(raw.get("education"))
    schools = education.get("schools") if isinstance(education, dict) else None
    if not isinstance(schools, list):
        return []
    entries: List[EducationEntry] = []
    seen: set = set()  # (institution, degree, start_date, end_date), lowercased
    for school in schools:
        if not isinstance(school, dict):
            continue
        # Confirmed live shape (not documentation-guessed): "school" is the
        # institution name, "degree" the degree, dates are "start_year"/
        # "end_year" (ints), and there is no separate field_of_study key —
        # it sometimes appears embedded in "degree" or "description" text
        # instead, never guessed at here.
        start_year = school.get("start_year")
        end_year = school.get("end_year")
        entry = EducationEntry(
            institution=_clean(school.get("school")) or _clean(school.get("name")) or _clean(school.get("institution")),
            degree=_clean(school.get("degree")) or _clean(school.get("degree_name")),
            field_of_study=_clean(school.get("field_of_study")) or _clean(school.get("field")),
            start_date=str(start_year) if start_year is not None else None,
            end_date=str(end_year) if end_year is not None else None,
            description=_clean(school.get("description")),
        )
        # CrustData was observed live to return the exact same school entry
        # twice (same institution/degree/dates) for a real candidate — a
        # provider-side duplicate, not a second real credential. Deduping on
        # the identifying fields (ignoring description, which can differ in
        # formatting for an otherwise-identical entry) keeps one copy.
        dedup_key = ((entry.institution or "").lower(), (entry.degree or "").lower(), entry.start_date, entry.end_date)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        entries.append(entry)
    return entries


def _parse_contact(raw: Dict[str, Any], candidate: Candidate) -> ContactEvidence:
    contact = _coerce_mapping(raw.get("contact"))
    return ContactEvidence(
        email=candidate.email,
        phone=candidate.phone,
        has_business_email=contact.get("has_business_email") if isinstance(contact, dict) else None,
    )


def _clean_harvest_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _apply_harvest_normalization(evidence: CandidateEvidence, harvest: HarvestEvidence) -> None:
    """Extracts employment descriptions/projects/certifications/skills from
    a successful Harvest response into CandidateEvidence's harvest_* fields
    — structured, never destructively merged with the CrustData fields.
    Only ever called with harvest.success is True; a failed/absent
    enrichment leaves these fields at their empty defaults, which is itself
    correct (no evidence, not negative evidence)."""
    element = harvest.raw.get("element") if isinstance(harvest.raw, dict) else None
    if not isinstance(element, dict):
        return

    for entry in element.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        description = _clean_harvest_text(entry.get("description"))
        if not description:
            continue
        position = _clean_harvest_text(entry.get("position")) or "role"
        company = _clean_harvest_text(entry.get("companyName"))
        role_label = f"{position} at {company}" if company else position
        evidence.harvest_employment_descriptions.append((role_label, description))

    for entry in element.get("projects") or []:
        if not isinstance(entry, dict):
            continue
        title = _clean_harvest_text(entry.get("title"))
        if not title:
            continue
        description = _clean_harvest_text(entry.get("description")) or ""
        evidence.harvest_projects.append((title, description))

    for entry in element.get("certifications") or []:
        if not isinstance(entry, dict):
            continue
        title = _clean_harvest_text(entry.get("title"))
        if title:
            evidence.harvest_certifications.append(title)

    skill_names: List[str] = []
    for entry in element.get("skills") or []:
        if isinstance(entry, dict):
            name = _clean_harvest_text(entry.get("name"))
            if name:
                skill_names.append(name)
    for name in element.get("topSkills") or []:
        cleaned = _clean_harvest_text(name)
        if cleaned:
            skill_names.append(cleaned)
    # Dedupe while preserving order (topSkills often repeats entries from skills[]).
    seen_skills: set = set()
    for name in skill_names:
        key = name.lower()
        if key not in seen_skills:
            seen_skills.add(key)
            evidence.harvest_skills.append(name)

    about = _clean_harvest_text(element.get("about"))
    evidence.harvest_about = about
    if about:
        match = _SELF_REPORTED_YEARS_RE.search(about)
        if match:
            evidence.harvest_self_reported_experience = (
                f"Candidate's own profile summary states \"{match.group(0)}\" — self-reported, not verified."
            )


def build_candidate_evidence(
    candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence] = None
) -> CandidateEvidence:
    raw = candidate.raw_data or {}
    basic_profile = _coerce_mapping(raw.get("basic_profile"))
    experience = _coerce_mapping(raw.get("experience"))
    employment_details = _coerce_mapping(experience.get("employment_details"))
    current_list = employment_details.get("current") or []
    current = current_list[0] if current_list and isinstance(current_list[0], dict) else {}
    past_roles = _parse_past_roles(employment_details.get("past"))

    metadata = _coerce_mapping(raw.get("metadata"))
    matched_queries = raw.get("matched_queries")
    matched_queries = [q for q in matched_queries if isinstance(q, str)] if isinstance(matched_queries, list) else []

    fit_value = raw.get("fit")
    fit_value = fit_value if isinstance(fit_value, str) else None

    evidence = CandidateEvidence(
        candidate_id=candidate.candidate_id or "",
        name=candidate.name or "",
        current_title=candidate.title or "",
        headline=basic_profile.get("headline") or "",
        profile_url=candidate.profile_url,
        location=candidate.location or "",
        current_company=candidate.company or "",
        current_industries=[i for i in (current.get("company_industries") or []) if isinstance(i, str)],
        current_function=current.get("function_category"),
        current_seniority=current.get("seniority_level"),
        current_headcount=current.get("company_headcount_range"),
        current_company_type=current.get("company_type"),
        past_roles=past_roles,
        education=_parse_education(raw),
        contact=_parse_contact(raw, candidate),
        search_evidence=SearchEvidence(
            matched_queries=list(set(matched_queries)),
            convergence=len(set(matched_queries)) > 1,
            provider_fit=fit_value,
        ),
        updated_at=metadata.get("updated_at") if isinstance(metadata, dict) else None,
        harvest=harvest_evidence,
    )

    if harvest_evidence is not None and harvest_evidence.success:
        _apply_harvest_normalization(evidence, harvest_evidence)

    evidence.derived_experience_years = _derive_experience_years(current, past_roles)
    judgments = raw.get("__requirement_judgments")
    evidence.requirement_judgments = judgments if isinstance(judgments, list) else None

    evidence.role_alignment = _build_role_alignment(evidence, intent)
    evidence.uncertainty = _build_uncertainty(evidence)
    return evidence


def _build_uncertainty(evidence: CandidateEvidence) -> List[UncertaintyNote]:
    notes = [
        UncertaintyNote(
            field="years_of_experience",
            note="Total years of professional experience is not independently verified. "
            + (
                f"About {evidence.derived_experience_years:g} years of professional experience are visible in "
                "dated roles (all roles combined); years in a specific discipline are not verified. "
                if evidence.derived_experience_years is not None
                else "No dated roles were available to estimate it. "
            )
            + (
                "A self-reported figure appears in the candidate's own profile summary (see below) but is not verified."
                if evidence.harvest_self_reported_experience
                else "No self-reported figure was found either."
            ),
        ),
        UncertaintyNote(
            field="skills",
            note=(
                "Skills are as the candidate listed them on their profile; anything not listed there is only what "
                "appears literally in title/headline/career history text."
                if evidence.harvest_skills
                else "A skills list was not available for this candidate; any technology mentioned above is only "
                "what appears literally in the candidate's title, headline, or career history text."
            ),
        ),
    ]
    if not evidence.education:
        notes.append(
            UncertaintyNote(
                field="education",
                note="Education was not returned for this candidate in this search's response.",
            )
        )
    if not evidence.updated_at:
        notes.append(
            UncertaintyNote(
                field="updated_at",
                note="This candidate's profile-updated date was not returned in this search's response.",
            )
        )
    return notes
