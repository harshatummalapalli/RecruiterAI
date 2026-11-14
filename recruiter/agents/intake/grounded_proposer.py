"""Web-GROUNDED capability proposer — frontier-model domain intelligence at intake.

The closed-book proposer (llm_proposer.py) can only emit domain knowledge the base
model already holds, so for a niche role it has never seen (eDiscovery/Relativity, a
payments rail, a vertical SDK) it goes broad and the search falls back to title+geo.
This proposer instead RESEARCHES the role on the open web + vendor docs and returns
the builder-only evidence vocabulary a genuine practitioner's profile carries.

Slice 1 — COMPOSITION. A specialized role is usually not one axis but several
REQUIRED dimensions: a DOMAIN capability AND the CRAFT/stack that proves the person
BUILDS it rather than merely uses it (a Relativity *developer*, not a Relativity
reviewer). We return one dimension per axis; each becomes its own hard keyword group
(BriefingAgent turns capability_groups into must_have_keyword_groups, briefing/agent.py),
and briefing AND-s them — so the set is Relativity ∩ .NET/SQL-development, not every
profile that merely mentions Relativity. The languages/stack are KEPT on the craft
dimension (keep_languages) precisely because dropping them is what let analysts and
support staff into the set.

Returns a tuple of CapabilityDimension (domain-first), which CapabilityProposer folds
into the cached capability — same drop-in contract, no plumbing change. Rare (once per
new role shape, then cached). Fail-safe: any failure, or a grounded 'broad' verdict,
returns () — the role stays broad rather than taking a wrong narrow guess.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from recruiter.agents.intake.capability_memory import CapabilityDimension
from recruiter.agents.intake.llm_proposer import _sanitize_terms

_log = logging.getLogger(__name__)

_STOP = {"of", "the", "a", "an", "and", "or", "for", "to", "in", "on"}


def _is_distinctive(token: str) -> bool:
    """A token with internal STRUCTURE that marks it as a specific name/acronym
    rather than a common word — a digit, a special char, ALL-CAPS (RSAPI, RDO,
    RAP), or internal capitals (RelativityOne, LangChain)."""
    t = (token or "").strip()
    if not t:
        return False
    if any(ch.isdigit() for ch in t) or any(ch in "#./+" for ch in t):
        return True
    if t.isupper() and 2 <= len(t) <= 7 and any(c.isalpha() for c in t):
        return True
    return any(c.isupper() for c in t[1:])


def _is_domain_anchor(term: str, label: str) -> bool:
    """A DOMAIN term is a usable hard anchor only if it is specific to the domain:
    some word is distinctively structured (an acronym/product like RSAPI/RDO), OR
    it shares a word with the domain's own label (e.g. "Relativity Object Model"
    carries "Relativity"). A term made of plain generic words with no tie to the
    domain ("Application Deployment System") is NOT an anchor — it would only add
    noise to the OR — so it is kept out of the hard group. This is a principled
    rule, not a word blocklist: the domain's label IS the anchor set."""
    label_words = {w.lower() for w in re.split(r"[\s/]+", label or "") if w and w.lower() not in _STOP}
    words = [w for w in re.split(r"[\s/]+", (term or "").strip()) if w and w.lower() not in _STOP]
    return any(_is_distinctive(w) or w.lower() in label_words for w in words)

_SYSTEM = (
    "You are a technical sourcing researcher. Given a role, work out what it ACTUALLY "
    "requires — the real problem behind the words — and decompose it into the REQUIRED "
    "DIMENSIONS a genuine practitioner's profile must evidence. USE WEB SEARCH against "
    "official/vendor docs and real practitioner sources before answering; do NOT rely on "
    "memory for niche domains.\n\n"
    "Most specialized roles are a COMPOSITION, not one axis:\n"
    "- a DOMAIN dimension — the specialization itself (the platform, product, field), named "
    "by API/SDK/component/acronym tokens only a real builder of it would carry;\n"
    "- a CRAFT dimension — the languages/stack that prove the person BUILDS the domain rather "
    "than merely USES it (for a Relativity *developer*: C#, .NET, SQL — NOT for a reviewer).\n\n"
    "CRITICAL — mark which dimensions actually GATE the match with `required`:\n"
    "- required=true ONLY for the few dimensions a candidate MUST evidence to be worth looking "
    "at: the domain specialization the hiring manager insists on, and the core craft/stack for "
    "the primary job. MOST ROLES HAVE 1-2 REQUIRED DIMENSIONS.\n"
    "- required=false for everything the posting merely lists as useful, preferred, 'a plus', or "
    "a secondary/adjacent stack (e.g. a cloud provider, a nice-to-have ML framework, DevOps "
    "tooling). These still inform ranking; they must NOT be hard filters.\n"
    "- Over-requiring is the main failure mode: requiring every listed technology AND-ed together "
    "returns NO ONE. When unsure, mark required=false.\n\n"
    "Return ONLY one JSON object:\n"
    '{"broad": bool, "dimensions": [{"label": str, "kind": "domain"|"craft"|"other", '
    '"required": bool, "terms": [str]}]}\n'
    "- broad=true ONLY when the role has no single defining specialization (a plain 'Backend "
    "Engineer' with no domain). Then dimensions is ignored.\n"
    "- label: a short name for the dimension, never the job title.\n"
    "- DOMAIN terms: 5-10 SPECIFIC, profile-searchable tokens ONLY a real builder would carry — "
    "API/SDK names, framework/component names, domain acronyms. NOT programming languages, NOT "
    "generic engineering words, NOT the job title.\n"
    "- CRAFT terms: the actual languages/frameworks/stack the build requires (C#, .NET, ASP.NET, "
    "SQL Server, T-SQL...). On a craft dimension these ARE the evidence — include them.\n"
    "- back the domain vocabulary with sources you actually found; if the web does not support a "
    "specific domain vocabulary, return broad=true.\n\n"
    "Example — a hiring manager insists on 'prior Relativity API experience', in a JD for a "
    ".NET/C# engineer that ALSO lists Azure, some AI/ML, Python and Docker as useful: after "
    "research you return (note only the core two are required)\n"
    '{"broad": false, "dimensions": ['
    '{"label": "Relativity Platform Development", "kind": "domain", "required": true, "terms": '
    '["Relativity","RelativityOne","RSAPI","Kepler","RDO","Relativity Dynamic Objects"]},'
    '{"label": ".NET / SQL Development", "kind": "craft", "required": true, "terms": ["C#",".NET","ASP.NET","SQL Server","T-SQL"]},'
    '{"label": "AI / ML", "kind": "other", "required": false, "terms": ["RAG","LLM","LangChain"]},'
    '{"label": "Cloud / DevOps", "kind": "other", "required": false, "terms": ["Azure","Docker","Kubernetes"]}]}'
)


def _user_prompt(identity: str, posted_title: Optional[str], requirement_texts: List[str]) -> str:
    lines = [f"Role identity: {identity}"]
    if posted_title and posted_title != identity:
        lines.append(f"Posted title: {posted_title}")
    if requirement_texts:
        lines.append("Requirements / hiring-manager signals: " + "; ".join(requirement_texts))
    return "\n".join(lines) + "\n\nResearch the role, then return the JSON now."


def _parse(data, identity: str) -> Tuple[CapabilityDimension, ...]:
    """Map the grounded research JSON to required dimensions, DOMAIN-first (so the
    primary/corroboration signal is the domain, not the craft). A craft dimension
    keeps its languages; a domain dimension strips incidental ones. Drops any
    dimension left empty after sanitizing; broad / no usable dimension -> ()."""
    if not isinstance(data, dict) or data.get("broad"):
        return ()
    # (kind, required, dim) per parsed dimension, before required/supporting routing.
    parsed: List[Tuple[str, bool, CapabilityDimension]] = []
    dropped: List[str] = []       # domain terms rejected as non-anchors (for the note)
    supporting: List[str] = []    # dimension labels demoted to rank-only (for the note)
    for d in (data.get("dimensions") or []):
        if not isinstance(d, dict):
            continue
        label = (d.get("label") or "").strip()
        kind = (d.get("kind") or "").strip().lower()
        required = bool(d.get("required", kind in ("domain", "craft")))  # fallback if omitted
        raw = [t for t in (d.get("terms") or []) if isinstance(t, str) and t.strip()]
        # Craft dimension: the languages/stack ARE the evidence — keep them.
        terms = _sanitize_terms(raw, identity, label, keep_languages=(kind == "craft"))
        if kind == "domain":
            # Admit to the hard keyword group only distinctive-anchored terms; a
            # generic-only term ("Object Manager") would just add noise to the OR.
            kept = [t for t in terms if _is_domain_anchor(t, label)]
            dropped += [t for t in terms if t not in kept]
            terms = kept
        if not label or not terms:
            continue
        parsed.append((kind, required, CapabilityDimension(
            label=label, terms=tuple(dict.fromkeys(terms)), source_qualifier=label)))

    # HARD vs RANK-ONLY: only REQUIRED dimensions become hard keyword groups. A
    # role that lists many useful technologies would otherwise AND them all and
    # return no one; the supporting ones still inform ranking via the requirements.
    hard = [(k, dim) for (k, req, dim) in parsed if req]
    if not hard:  # nothing marked -> fall back to the domain/craft core, not everything
        hard = [(k, dim) for (k, req, dim) in parsed if k in ("domain", "craft")]
    supporting = [dim.label for (k, req, dim) in parsed if (k, dim) not in hard]
    # Domain-first, and cap the hard groups so an over-eager proposal can't AND the
    # set down to nothing (prefer domain, then craft, then any other required).
    order = {"domain": 0, "craft": 1}
    hard.sort(key=lambda kd: order.get(kd[0], 2))
    dims = tuple(dim for _, dim in hard[:3])
    _log_feasibility_note(identity, dims, dropped, supporting)
    return dims


def _log_feasibility_note(identity: str, dims: Tuple[CapabilityDimension, ...],
                          dropped: List[str], supporting: List[str]) -> None:
    """Internal honesty note (logged, not a UI): the hard-filter strategy this
    role resolved to, the dimensions demoted to rank-only, the domain terms
    dropped as non-anchors, and the standing residual that CrustData cannot
    express — so a reader knows what the set does and does NOT guarantee, and the
    ranking pass knows what it must still judge."""
    if not dims:
        _log.info("capability feasibility [%s]: no hard dimension — role stays broad", identity)
        return
    groups = " AND ".join(f"{d.label}({'|'.join(d.terms)})" for d in dims)
    note = f"capability feasibility [{identity}]: hard groups = {groups}"
    if supporting:
        note += f"; rank-only (NOT hard-filtered — too broad/secondary to gate): {', '.join(supporting)}"
    if dropped:
        note += f"; domain terms dropped as non-anchors: {', '.join(dropped)}"
    if len(dims) >= 2:
        note += ("; RESIDUAL (not keyword-expressible): builder-vs-user of the domain cannot be "
                 "proven from CrustData fields — approximated by requiring the craft co-constraint, "
                 "resolved in the ranking read.")
    _log.info("%s", note)


def make_grounded_proposer(model: str = "claude-sonnet-5-5", research=None):
    """Returns an LlmProposer: (identity, posted_title, requirement_texts) ->
    tuple of CapabilityDimension (domain-first) | (), backed by a web-grounded
    Claude call. `research` is the (system, user, model) -> (dict, sources) fn
    (default: recruiter.llm.core.research_json); injectable so tests run fully
    offline. Any failure -> () (role stays broad)."""

    def propose(identity: str, posted_title: Optional[str], requirement_texts: List[str]) -> Tuple[CapabilityDimension, ...]:
        fn = research
        if fn is None:
            from recruiter.llm.core import research_json
            fn = research_json
        try:
            data, _sources = fn(_SYSTEM, _user_prompt(identity, posted_title, list(requirement_texts)), model)
        except Exception:
            return ()
        return _parse(data, identity)

    return propose
