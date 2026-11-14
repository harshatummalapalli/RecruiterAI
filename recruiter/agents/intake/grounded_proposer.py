"""Web-GROUNDED capability proposer — frontier-model domain intelligence at intake.

The closed-book proposer (llm_proposer.py) can only emit domain knowledge the base
model already holds, so for a niche role it has never seen (eDiscovery/Relativity, a
payments rail, a vertical SDK) it goes broad and the search falls back to title+geo.
This proposer instead RESEARCHES the role on the open web + vendor docs and returns
the builder-only evidence vocabulary a genuine practitioner's profile carries — the
terms that then become a HARD keyword filter (BriefingAgent turns capability_groups
into must_have_keyword_groups, briefing/agent.py) AND lead the NL ranking
(briefing/query.py). This is the intelligence that works even when the recruiter
doesn't know what to search for.

Same `LlmProposer` signature as the closed-book proposer, so it drops into the
existing CapabilityProposer with NO plumbing change. Rare (once per new role shape,
then cached in capability memory). Fail-safe: any failure, or a grounded 'broad'
verdict, returns None — the role stays broad rather than taking a wrong narrow guess.
"""

from __future__ import annotations

from typing import List, Optional

from recruiter.agents.intake.capability_memory import LearnedCapability
from recruiter.agents.intake.llm_proposer import _sanitize_terms

_SYSTEM = (
    "You are a technical sourcing researcher. Given a role, work out what it ACTUALLY "
    "requires — the real problem behind the words — and the EVIDENCE VOCABULARY a genuine "
    "practitioner's profile would contain. USE WEB SEARCH against official/vendor docs and "
    "real practitioner sources before answering; do NOT rely on memory for niche domains.\n\n"
    "Return ONLY one JSON object:\n"
    '{"broad": bool, "label": str, "qualifier": str, "strong_terms": [str], "weak_terms": [str], '
    '"anti_signals": [str], "employer_pools": [str], "titles": [str], "certifications": [str], '
    '"screening_questions": [str], "sources": [{"claim": str, "url": str}]}\n'
    "- broad=true ONLY when the role has no single defining specialization (a plain 'Backend "
    "Engineer' with no domain). Then the other fields are ignored.\n"
    "- label: a short CAPABILITY name, never a job title.\n"
    "- strong_terms: 5-12 SPECIFIC, profile-searchable tokens that ONLY a real builder of this "
    "capability would carry — API/SDK names, framework/component names, domain acronyms. NOT "
    "programming languages, NOT generic engineering words, NOT the job title.\n"
    "- anti_signals: terms that look similar but indicate the WRONG person (a user/reviewer, not a builder).\n"
    "- employer_pools: the kinds of companies where this talent concentrates.\n"
    "- back every strong_term and claim with a source URL you actually found; if the web does not "
    "support a specific vocabulary, return broad=true.\n\n"
    "Example — a hiring manager wants 'Relativity API experience, converting SQL to .NET': after "
    'research you would return label "Relativity Platform Development", strong_terms like '
    '["Relativity","RelativityOne","Object Manager API","Kepler","RSAPI","Event Handlers","RDO",'
    '"RAP","IDBContext"], anti_signals like ["document review","Relativity reviewer"], employer_pools '
    'like ["eDiscovery vendors","AmLaw 100 law firms","Big Four forensics"].'
)


def _user_prompt(identity: str, posted_title: Optional[str], requirement_texts: List[str]) -> str:
    lines = [f"Role identity: {identity}"]
    if posted_title and posted_title != identity:
        lines.append(f"Posted title: {posted_title}")
    if requirement_texts:
        lines.append("Requirements / hiring-manager signals: " + "; ".join(requirement_texts))
    return "\n".join(lines) + "\n\nResearch the role, then return the JSON now."


def _parse(data, identity: str) -> Optional[LearnedCapability]:
    """Map the grounded research JSON to a LearnedCapability for the EXISTING
    capability path: the strong terms become the group's terms (hard keyword filter
    + NL lead). The richer fields (anti-signals, pools, screening questions, sources)
    are carried by the research JSON for a later increment; increment 1 keeps the
    LearnedCapability contract so nothing downstream changes."""
    if not isinstance(data, dict) or data.get("broad"):
        return None
    label = (data.get("label") or "").strip()
    raw = [t for t in (data.get("strong_terms") or []) if isinstance(t, str) and t.strip()]
    # Same deterministic backstop the closed-book proposer uses: drop the job title
    # and generic tokens (languages, "software", ...) so only real evidence survives.
    terms = _sanitize_terms(raw, identity, label)
    if not label or not terms:
        return None
    qualifier = (data.get("qualifier") or "").strip() or label
    return LearnedCapability("", label, tuple(dict.fromkeys(terms)), qualifier)


def make_grounded_proposer(model: str = "claude-sonnet-5-5", research=None):
    """Returns an LlmProposer: (identity, posted_title, requirement_texts) ->
    LearnedCapability | None, backed by a web-grounded Claude call. `research` is the
    (system, user, model) -> (dict, sources) fn (default: recruiter.llm.core.research_json);
    injectable so tests run fully offline. Any failure -> None (role stays broad)."""

    def propose(identity: str, posted_title: Optional[str], requirement_texts: List[str]) -> Optional[LearnedCapability]:
        fn = research
        if fn is None:
            from recruiter.llm.core import research_json
            fn = research_json
        try:
            data, _sources = fn(_SYSTEM, _user_prompt(identity, posted_title, list(requirement_texts)), model)
        except Exception:
            return None
        return _parse(data, identity)

    return propose
