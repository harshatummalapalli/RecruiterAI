"""Requirement judge — decides, per candidate, which of the search's own
Core/Supporting/Differentiator requirements the candidate's profile actually
evidences, and PROVES each "met" with a quote.

Why this exists: deterministic term matching (candidate_evidence_builder)
picks generic words out of requirement sentences and produced confident wrong
matches on a real search (a "relational databases" requirement matched the word
"design" in "system design discussions"; a "3+ years" requirement matched the
word "backend"). Here a small model judges the requirement's MEANING, and its
answer only counts if it can point at a passage of the profile and quote it:

  * The quote must appear, verbatim (whitespace/case-insensitive), inside the
    passage it cites. A fabricated or paraphrased quote is discarded and the
    requirement is treated as not evidenced.
  * Passages are the same text sources the evidence engine already trusts
    (role descriptions, projects, certifications, headline, titles, skills),
    plus one generated "career dates" passage so a years requirement can be
    judged from dates instead of a keyword.

Any failure (no API key, network error, unparseable output) returns None and
the caller keeps the deterministic engine — a judge outage never breaks a
search.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI

from backend.config import get_openai_api_key
from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence, TextSource
from backend.models.search_intent import SearchIntent
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.requirement_semantics import evaluate as evaluate_recognized_requirement, recognize_requirement

logger = logging.getLogger(__name__)

# Parallel single-claim review calls per candidate (the pipeline already runs several candidates at once).
REVIEW_CONCURRENCY = 4
JUDGE_MODEL = "gpt-4o-mini"
# OpenAI list price per 1M tokens for gpt-4o-mini, used ONLY to estimate spend
# in internal diagnostics. An assumption to re-check against the current price
# sheet, not a billing figure.
INPUT_USD_PER_MILLION_TOKENS = 0.15
OUTPUT_USD_PER_MILLION_TOKENS = 0.60
MAX_PASSAGES = 30
MAX_PASSAGE_CHARS = 900

_SYSTEM_PROMPT = """You read a candidate's whole profile and decide, like an experienced recruiter, whether their career shows each hiring requirement.

You get numbered PASSAGES copied from the candidate's profile — their job TITLES, a headline, and the descriptions and skills under their roles — and numbered REQUIREMENTS from the job. Read all the passages together as one career before you judge; a single role title or line can decide a requirement.

For every requirement decide:
- "met": the career clearly shows the requirement's CORE capability — the main skill, tool, or kind of work it names. Judge on that primary subject; extra qualifiers the requirement lists (for example "consolidation and modernization", or a long protocol list like "SSO, MFA, SAML, OAuth/OIDC, RBAC") are added depth, NOT things that each have to appear.
- "partly": the career shows something adjacent to the core, but not the core itself.
- "not_evidenced": nothing in the career shows it.

How to weigh the evidence:
1. A role's JOB TITLE is real evidence. Someone titled "Manager, Identity and Access Management" or "Sr. IAM Applications Analyst" has done IAM work, even when that role carries no description — many strong profiles list senior roles with little text. Quote the title in that case.
2. A description line that states the requirement's core capability is the strongest evidence.
3. Judge MEANING, not keywords. A shared generic word is not evidence: "design" does not show database schema design, "applications" does not show AI/ML. And an EMPLOYER or its prestige is never evidence of a skill — "Engineer at Google" does not show IAM; only what the person themselves did counts.

Rules:
- For "met" and "partly" give the passage number and a quote copied EXACTLY, character for character, from that passage (at most 220 characters) — the quote may be a role TITLE or a line from a description. Never paraphrase. If you cannot quote a title or line that carries the core, answer "not_evidenced".
- "term" is the 1-4 word phrase inside your quote that carries the evidence, copied exactly.
- A duration requirement (for example "3+ years") is judged only from the passage labelled "career dates" — TOTAL professional experience across all roles, not years in one discipline.
- Use only the passages, not outside knowledge about the person or their employers.
- If several passages qualify, cite the one that shows the requirement's core most directly.

Return only JSON: {"results":[{"r":<requirement number>,"verdict":"met|partly|not_evidenced","p":<passage number or null>,"quote":"<exact quote or empty>","term":"<exact phrase or empty>"}]}
Include every requirement exactly once."""


_PUNCTUATION_FOLD = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " ",
        "\u2022": " ", "\u00b7": " ", "\u25aa": " ", "\u2023": " ",
    }
)


def _normalize(text: str) -> str:
    """Comparison form used ONLY to decide whether a quote appears in a
    passage: curly quotes/dashes folded, bullet glyphs and NBSP dropped,
    whitespace collapsed, case ignored. Both sides are normalized the same
    way, so a model dropping a leading bullet or straightening a quote still
    verifies, while a changed or invented word never does."""
    return re.sub(r"\s+", " ", (text or "").translate(_PUNCTUATION_FOLD)).strip().casefold()


_REVIEW_PROMPT = """You review whether a quote from a candidate's profile is genuine evidence for a hiring requirement.

For each CLAIM you get a job REQUIREMENT and a QUOTE — which may be a role's job TITLE or a line from a role description.
Judge each claim on its own: does the QUOTE, read by itself, show the candidate did or worked in the requirement's
ESSENTIAL subject?

supports=true when the quote names the requirement's own essential subject — the skill, tool or kind of work at its
heart — INCLUDING a job title that names it (title "Manager, Identity and Access Management" supports an IAM
requirement; "Sr. Database Engineer" supports a databases requirement). A named tool of that kind counts (Okta or
Entra ID for identity, Docker for containers, PostgreSQL for relational databases). The requirement's secondary
qualifiers do NOT each have to be restated: who consumes the work, scale, sub-activities such as "consolidation and
modernization", or every item in a long enumeration (SSO, MFA, SAML, OAuth/OIDC, RBAC).

supports=false when the quote:
- is about a different subject, or fits almost any role (designing systems, running infrastructure, working on
  services) without naming the requirement's own subject;
- drops the requirement's DISTINGUISHING subject for a broader word — "APIs" for "GraphQL APIs", "identity" for
  "privileged access management", "data" for "relational databases";
- is only the employer's name or prestige, not what the person did;
- describes meeting, planning, scoping or intending to do the work rather than having done it.

Examples: requirement "Active Directory management, consolidation, and modernization" with quote "Managed Active
Directory environments for security compliance" is supports=true (names the core; consolidation and modernization are
depth). Requirement "Experience with GraphQL APIs" with quote "Built high-performance APIs" is supports=false (never
says GraphQL).

Return only JSON: {"results":[{"i":<claim number>,"supports":true|false}]}
Include every claim exactly once."""


CAREER_DATES_CAVEAT = (
    "This is total experience across all roles; years in any one specific discipline are not independently verified."
)


def _career_dates_sentence(years: float) -> str:
    return f"About {years:g} years of professional experience are visible in dated roles."


def _career_dates_passage(evidence) -> Optional[TextSource]:
    if evidence.derived_experience_years is None:
        return None
    lines = [_career_dates_sentence(evidence.derived_experience_years), CAREER_DATES_CAVEAT]
    for role in evidence.past_roles[:8]:
        start = (role.start_date or "")[:7]
        end = (role.end_date or "")[:7] or "present"
        if role.title or role.company:
            lines.append(f"{role.title or 'Role'} at {role.company or 'company'} ({start or '?'} to {end}).")
    return TextSource("career dates", " ".join(lines), "", "title_history", "supporting")


def build_passages(
    candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence] = None
) -> List[TextSource]:
    """The numbered profile passages the judge may cite: a generated "career
    dates" passage first (when dates exist), then every text source the
    evidence engine already trusts. Public so tests and diagnostics can
    address a passage by number exactly as the model sees it."""
    evidence = build_candidate_evidence(candidate, intent, harvest_evidence=harvest_evidence)
    passages: List[TextSource] = []
    dates = _career_dates_passage(evidence)
    if dates:
        passages.append(dates)
    passages.extend(evidence.labeled_text_sources())
    return [p for p in passages if (p.text or "").strip()][:MAX_PASSAGES]


@dataclass
class JudgeOutcome:
    """The judgments (None = judge unavailable/failed, caller falls back) plus
    what the call cost, for internal diagnostics."""

    judgments: Optional[List[Dict[str, Any]]]
    requirements: int = 0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    failed: bool = False
    # True when the second-pass review call itself failed, so first-pass verdicts stand unreviewed.
    review_failed: bool = False
    downgraded_by_review: int = 0
    re_asked_missing: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.input_tokens * INPUT_USD_PER_MILLION_TOKENS + self.output_tokens * OUTPUT_USD_PER_MILLION_TOKENS
        ) / 1_000_000


class RequirementJudge:
    """`client` is injectable for tests, mirroring OpenAIProvider/IntakeReasoner."""

    def __init__(self, client: Optional[OpenAI] = None, model: str = JUDGE_MODEL) -> None:
        self._client = client
        self._model = model

    def is_available(self) -> bool:
        return self._client is not None or bool(get_openai_api_key())

    def judge(
        self, candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence] = None
    ) -> Optional[List[Dict[str, Any]]]:
        return self.judge_detailed(candidate, intent, harvest_evidence).judgments

    def judge_detailed(
        self, candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence] = None
    ) -> JudgeOutcome:
        started = time.perf_counter()
        outcome = self._judge(candidate, intent, harvest_evidence)
        outcome.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return outcome

    def _judge(
        self, candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence]
    ) -> JudgeOutcome:
        requirements = (
            [("core", s) for s in intent.core_signals]
            + [("supporting", s) for s in intent.supporting_signals]
            + [("differentiator", s) for s in intent.differentiator_signals]
        )
        if not requirements:
            return JudgeOutcome(judgments=None)
        outcome = JudgeOutcome(judgments=None, requirements=len(requirements))
        try:
            # Deterministic pre-pass: a requirement whose own wording
            # unambiguously names a validated company-size/industry/career-
            # progression pattern (see requirement_semantics.py) is answered
            # directly from career_signals.py and never sent to the LLM at
            # all — everything else falls through to the existing judge path
            # below, completely unchanged. Inside this try block on purpose:
            # a failure here must degrade exactly like any other judge
            # failure, never break the search.
            deterministic: Dict[int, Dict[str, Any]] = {}
            for i, (tier, text) in enumerate(requirements):
                recognized = recognize_requirement(text)
                if recognized is not None:
                    deterministic[i] = evaluate_recognized_requirement(recognized, tier, candidate, harvest_evidence)
            remaining = [i for i in range(len(requirements)) if i not in deterministic]

            if not remaining:
                outcome.judgments = [deterministic[i] for i in range(len(requirements))]
                return outcome

            passages = build_passages(candidate, intent, harvest_evidence)
            if not passages:
                outcome.judgments = [
                    deterministic[i] if i in deterministic else self._not_evidenced(tier, text)
                    for i, (tier, text) in enumerate(requirements)
                ]
                return outcome

            client = self._client or OpenAI(api_key=get_openai_api_key())
            results: Dict[int, Dict[str, Any]] = {}
            pending = list(remaining)
            # The model sometimes answers only some of the requirements (seen
            # live: 3 of 12 on one call, 12 of 12 on the next, same input).
            # A silently missing answer would read as "not evidenced" and
            # randomly under-rank a candidate, so ask again for just the
            # missing ones, once.
            for attempt in range(2):
                if not pending:
                    break
                answered = self._ask(client, passages, [(i, requirements[i][1]) for i in pending], outcome)
                if answered is None:
                    outcome.failed = True
                    return outcome
                results.update(answered)
                pending = [i for i in pending if i not in results]
                if pending and attempt == 0:
                    outcome.re_asked_missing += len(pending)
            outcome.judgments = [
                deterministic[i] if i in deterministic else self._verified(i, tier, text, results.get(i), passages)
                for i, (tier, text) in enumerate(requirements)
            ]
            self._review(client, outcome)
            return outcome
        except Exception:  # noqa: BLE001 - a judge failure must never break a search
            logger.warning("Requirement judge failed; falling back to term matching | candidate_id=%s", candidate.candidate_id, exc_info=True)
            outcome.judgments = None
            outcome.failed = True
            return outcome

    def _review(self, client: Any, outcome: JudgeOutcome) -> None:
        """Second pass. The first pass sees every passage at once and can pick
        a real-but-irrelevant quote for a requirement (found live: a "REST
        APIs" requirement backed by a sentence about AWS infrastructure). A
        quote's existence is verified deterministically; whether it MEANS what
        was claimed is asked here, of a reviewer that sees only the
        requirement and the quote. Anything not affirmed is downgraded to
        "partly", which never counts as evidence. The generated career-dates
        claim is exempt (it is computed, not model-quoted).

        Each claim is reviewed in its own call: measured on real quotes, the
        same claim got different verdicts depending on which other claims
        shared its call, while a single-claim call was stable across repeats.
        If a review call itself fails, that claim's first-pass verdict stands
        and the failure is recorded."""
        claims = [
            (index, judgment)
            for index, judgment in enumerate(outcome.judgments or [])
            if judgment.get("verdict") == "met" and judgment.get("source") != "career dates" and not judgment.get("deterministic")
        ]
        if not claims:
            return

        def review_one(index: int, judgment: Dict[str, Any]) -> tuple:
            try:
                from recruiter.llm import complete_json  # provider-agnostic (OpenAI or Claude by model name)
                data = complete_json(
                    _REVIEW_PROMPT,
                    json.dumps({"claims": [{"i": index, "requirement": judgment["signal_text"], "quote": judgment["quote"]}]}, ensure_ascii=False),
                    self._model,
                    max_tokens=512,
                )
                reviewed = data.get("results", [])
                supported = any(
                    isinstance(r, dict) and r.get("i") == index and bool(r.get("supports")) for r in reviewed
                )
                return index, supported, None, None
            except Exception as exc:  # noqa: BLE001 - review failure keeps this claim's first-pass verdict
                return index, None, exc, None

        with ThreadPoolExecutor(max_workers=REVIEW_CONCURRENCY) as pool:
            results = list(pool.map(lambda item: review_one(*item), claims))
        for index, supported, error, usage in results:
            if error is not None:
                logger.warning("Requirement review call failed; first-pass verdict stands", exc_info=error)
                outcome.review_failed = True
                continue
            outcome.calls += 1
            outcome.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            outcome.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            if not supported:  # an omitted or unparseable answer is not affirmation
                judgment = outcome.judgments[index]
                judgment["verdict"] = "partly"
                judgment["review"] = "not_supported_by_quote_alone"
                outcome.downgraded_by_review += 1

    def _ask(
        self, client: Any, passages: List[TextSource], numbered: List[tuple], outcome: "JudgeOutcome"
    ) -> Optional[Dict[int, Dict[str, Any]]]:
        payload = {
            "passages": [
                {"p": i, "label": p.label, "text": (p.text or "")[:MAX_PASSAGE_CHARS]} for i, p in enumerate(passages)
            ],
            "requirements": [{"r": index, "text": text} for index, text in numbered],
        }
        from recruiter.llm import complete_json  # provider-agnostic (OpenAI or Claude by model name)
        outcome.calls += 1
        data = complete_json(_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False), self._model, max_tokens=2048)
        if not data:
            return None
        wanted = {index for index, _ in numbered}
        return {
            int(r["r"]): r
            for r in data.get("results", [])
            if isinstance(r, dict) and "r" in r and int(r["r"]) in wanted
        }

    @staticmethod
    def _not_evidenced(tier: str, text: str) -> Dict[str, Any]:
        return {"tier": tier, "signal_text": text, "verdict": "not_evidenced"}

    def _verified(
        self, index: int, tier: str, text: str, result: Optional[Dict[str, Any]], passages: List[TextSource]
    ) -> Dict[str, Any]:
        base = self._not_evidenced(tier, text)
        if not result or result.get("verdict") not in ("met", "partly"):
            return base
        quote = str(result.get("quote") or "").strip()
        try:
            passage = passages[int(result.get("p"))]
        except (TypeError, ValueError, IndexError):
            return base
        # THE gate: no quote that really appears in the cited passage, no credit.
        if len(quote) < 3 or _normalize(quote) not in _normalize(passage.text):
            logger.info("Discarded unverified quote for requirement %s", index)
            return base
        term = str(result.get("term") or "").strip()
        if not term or _normalize(term) not in _normalize(quote):
            term = " ".join(quote.split()[:3])
        detail = passage.detail
        if passage.label == "career dates":
            # A duration is satisfied by TOTAL dated experience only. The
            # recruiter-facing sentence is generated from the derived figure,
            # never from the model's wording, and always says what it is not.
            years = re.search(r"About ([\d.]+) years", passage.text)
            detail = f"{_career_dates_sentence(float(years.group(1)))} {CAREER_DATES_CAVEAT}" if years else CAREER_DATES_CAVEAT
        return {
            "tier": tier,
            "signal_text": text,
            "verdict": result["verdict"],
            "quote": quote,
            "term": term,
            "source": passage.label,
            "evidence_detail": detail,
            "evidence_type": passage.evidence_type,
            "strength": passage.strength,
        }
