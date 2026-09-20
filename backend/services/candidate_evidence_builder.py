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
from typing import Any, Dict, List, Optional, Tuple

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import (
    CandidateEvidence,
    ContactEvidence,
    EducationEntry,
    MatchedSignal,
    PastRole,
    RoleAlignment,
    SearchEvidence,
    UncertaintyNote,
)
from backend.models.search_intent import SearchIntent

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
}


def _words(text: Optional[str]) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _significant_words(text: Optional[str], min_len: int = 3) -> List[str]:
    return [w for w in _words(text) if len(w) >= min_len and w not in _STOPWORDS]


def _extract_signal_terms(sentence: str) -> List[str]:
    """Literal candidate terms to look for from one Core/Supporting/
    Differentiator sentence — significant words (>=4 chars, not a stopword,
    not a generic domain-restating noun) plus any capitalized multi-word
    phrase in the ORIGINAL sentence (e.g. "Terraform", "Solr",
    "OpenTelemetry"), lowercased for matching. This is generic text
    extraction, not a role-specific dictionary."""
    terms = set(w for w in _significant_words(sentence, min_len=4) if w not in _GENERIC_TERMS)
    for match in re.finditer(r"\b[A-Z][A-Za-z0-9+#.]{2,}\b", sentence):
        term = match.group(0).lower()
        if term not in _GENERIC_TERMS:
            terms.add(term)
    return sorted(terms)


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
        if ratio >= 0.6:
            return "direct", f"Current {source} shares the core term(s) {sorted(overlap)} with the target role."
        if ratio > 0:
            return "adjacent", f"Current {source} shares the term(s) {sorted(overlap)} with the target role, but not all of it."

    return "unclear", "Current title/headline has no clear textual overlap with the target role; not verified either way."


def _classify_seniority(candidate_seniority: Optional[str], target_seniority: Optional[str]) -> Tuple[Optional[bool], str]:
    if not target_seniority:
        return None, "No target seniority was specified for this search."
    if not candidate_seniority:
        return None, "Candidate's seniority level was not returned by the provider."
    candidate_norm = candidate_seniority.strip().lower()
    target_norm = target_seniority.strip().lower()
    if candidate_norm == target_norm or candidate_norm in target_norm or target_norm in candidate_norm:
        return True, f"Candidate's seniority level (\"{candidate_seniority}\") aligns with the target (\"{target_seniority}\")."
    return False, f"Candidate's seniority level (\"{candidate_seniority}\") does not match the target (\"{target_seniority}\")."


def _build_role_alignment(evidence: CandidateEvidence, intent: SearchIntent) -> RoleAlignment:
    title_relevance, title_basis = _classify_title_relevance(
        evidence.current_title, evidence.headline, intent.role.title, intent.titles.include_titles
    )
    seniority_alignment, seniority_basis = _classify_seniority(evidence.current_seniority, intent.role.seniority)

    # Sources are searched in order (current title, then headline, then past
    # roles from most to least recent) so that when a term appears in more
    # than one place, the explanation cites the most authoritative one —
    # this is what lets an explanation say "Headline mentions X" instead of
    # burying where the evidence actually came from in one flat text blob.
    sources = evidence.labeled_text_sources()
    matched: List[MatchedSignal] = []
    seen_matches: set = set()  # (tier, matched_term) — avoid duplicate bullets for the same literal term
    unmatched: List[MatchedSignal] = []
    tiered_signals = [
        ("core", intent.core_signals),
        ("supporting", intent.supporting_signals),
        ("differentiator", intent.differentiator_signals),
    ]
    for tier, sentences in tiered_signals:
        for sentence in sentences:
            terms = _extract_signal_terms(sentence)
            found_source, found_term = None, None
            for label, text in sources:
                text_lower = (text or "").lower()
                hit = next((term for term in terms if term in text_lower), None)
                if hit:
                    found_source, found_term = label, hit
                    break
            if found_term and (tier, found_term) not in seen_matches:
                seen_matches.add((tier, found_term))
                matched.append(MatchedSignal(tier=tier, signal_text=sentence, matched_term=found_term, source=found_source))
            elif not found_term:
                unmatched.append(MatchedSignal(tier=tier, signal_text=sentence, matched_term="", source=""))

    return RoleAlignment(
        title_relevance=title_relevance,
        title_relevance_basis=title_basis,
        seniority_alignment=seniority_alignment,
        seniority_alignment_basis=seniority_basis,
        matched_signals=matched,
        unmatched_signals=unmatched,
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


def build_candidate_evidence(candidate: Candidate, intent: SearchIntent) -> CandidateEvidence:
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
    )

    evidence.role_alignment = _build_role_alignment(evidence, intent)
    evidence.uncertainty = _build_uncertainty(evidence)
    return evidence


def _build_uncertainty(evidence: CandidateEvidence) -> List[UncertaintyNote]:
    notes = [
        UncertaintyNote(
            field="years_of_experience",
            note="Total years of professional experience is not returned by the data provider for any candidate.",
        ),
        UncertaintyNote(
            field="skills",
            note="Specific skills/technologies are not returned as a structured field; any technology mentioned "
            "above is only what appears literally in the candidate's title, headline, or career history text.",
        ),
    ]
    if not evidence.education:
        notes.append(
            UncertaintyNote(
                field="education",
                note="Education was not returned for this candidate in this search's response.",
            )
        )
    if evidence.search_evidence.provider_fit is None:
        notes.append(
            UncertaintyNote(
                field="fit",
                note="The provider's relevance signal (fit) was not returned for this candidate.",
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
