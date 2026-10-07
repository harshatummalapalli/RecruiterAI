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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from backend.config import get_openai_api_key
from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence, TextSource
from backend.models.search_intent import SearchIntent
from backend.services.candidate_evidence_builder import build_candidate_evidence
from backend.services.consumer_input import resolve as resolve_consumer_input
from backend.services.evidence_check import (DEPTH_ORDER, EVIDENCE_BASES, EvidenceCheck, INSUFFICIENT_EVIDENCE, NOT_PRESENT, OBSERVED_DEPTHS, PRESENT, RETRIABLE_QUOTE_FAILURES, WORK_EVIDENCE_TYPES,
                                             effective_depth, maximum_supported_depth, meets_depth, model_predicate, negative_checks, positive_checks, validate_binding, verify_quote)
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

_SYSTEM_PROMPT = """You verify whether a candidate's profile shows evidence for each hiring requirement.

You get numbered PASSAGES copied from the candidate's profile and numbered REQUIREMENTS from the job.
For every requirement decide:
- "met": a passage clearly demonstrates the requirement itself (the skill, tool, kind of work or duration it names).
- "partly": a passage shows something related but not the whole requirement.
- "not_evidenced": nothing in the passages demonstrates it.

Rules:
1. Judge the MEANING of the requirement. A shared generic word is not evidence: the word "design" does not evidence
   database schema design, "applications" does not evidence AI/ML, "backend" does not evidence years of experience.
2. For "met" and "partly" you MUST give the passage number and a quote copied EXACTLY, character for character,
   from that passage (at most 220 characters). Never paraphrase. If you cannot quote it, answer "not_evidenced".
3. "term" is the 1-4 word phrase inside your quote that carries the evidence, copied exactly.
4. A duration requirement (for example "3+ years") is judged only from the passage labelled "career dates". That passage
   gives TOTAL professional experience across all roles; it cannot show years in one specific discipline.
5. Do not use outside knowledge about the person or their employers.
6. The quote must itself state the requirement's own skill, tool, or kind of work. A tool or framework that COULD be
   used for the requirement is not evidence that it was used for it, and a related activity is at most "partly".
   If you would have to infer the requirement from general knowledge, answer "partly" or "not_evidenced".
7. If several passages qualify, cite the one that states it most directly.

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

For each CLAIM you get a job REQUIREMENT and a QUOTE. Judge every claim on its own, using only that requirement and
that quote. Decide whether the QUOTE, read by itself, shows the candidate did or used what the requirement names.

supports=true when the quote states the requirement's own skill, tool or kind of work. A named tool of the
requirement's own kind counts (Docker for containerized deployment, Kafka or RabbitMQ for message queues, PostgreSQL
or MySQL for relational databases, AWS/GCP/Azure for a cloud platform). Details such as who consumes the work, scale, or
"designing and implementing" do not each have to be restated.

supports=false when the quote:
- is about a different skill, tool or activity, or fits almost any engineering requirement (designing systems,
  running infrastructure, working on services) without naming the requirement's own subject;
- names a related tool, or a broader thing, without the requirement's distinguishing qualifier (for example "APIs" or
  "services" without REST, "data" or "an API" without relational databases);
- describes meeting, planning, scoping, assessing or intending to do the work rather than having done it;
- would only support the requirement if you inferred it from general knowledge.

Example of the qualifier rule: requirement "Experience with GraphQL APIs" with quote "Built high-performance APIs for
mobile clients" is supports=false, because the quote never says GraphQL. The same quote for "Experience building APIs"
is supports=true.

Return only JSON: {"results":[{"i":<claim number>,"supports":true|false}]}
Include every claim exactly once."""


_EXCLUSION_PROMPT = """You check whether a candidate's profile shows an EXCLUDED work identity.

You get numbered PASSAGES copied from the candidate's profile and numbered CHECKS. Each check is a predicate about the candidate's work identity: what work the
candidate actually does or did. Its fields:
- must_not_indicate: kinds of work or identity that exclude the candidate if the passages show the candidate has it.
- exclusive: if true, the check applies only when ALL the substantive work the passages show is of those kinds.
- unless_candidate_also_shows: if the passages show the candidate ALSO has any of these, the check does NOT apply.
- not_sufficient: things that NEVER make the check apply, however prominent.
- qualifier: a recruiter qualifier on the identity; keep it.

For every check decide:
- "present": the passages clearly show the candidate's work identity IS one of must_not_indicate, and no exclusive / unless_candidate_also_shows condition defeats it.
- "not_present": the passages describe the candidate's actual work in enough detail to say the check does not apply.
- "insufficient_evidence": the passages do not say enough about what work the candidate actually did to decide.

Rules:
1. Judge the work identity the passages show, not words. A mention of a topic, an employer in the field, training, or adjacent duties is not the identity.
2. Never broaden. Anything in not_sufficient never makes a check "present".
3. For "present" you MUST give the passage number and a quote copied EXACTLY, character for character, from that ONE passage: one contiguous span of at most
   220 characters, no ellipsis ("..." or "\u2026"), no paraphrase. The quote itself must show the work identity.
4. If you cannot give such a quote, do not answer "present": answer "insufficient_evidence".
5. Do not use outside knowledge about the person or their employers.

Return only JSON: {"results":[{"x":<check number>,"verdict":"present|not_present|insufficient_evidence","p":<passage number or null>,"quote":"<exact quote or empty>"}]}
Include every check exactly once."""


_DEPTH_PROMPT = """You read a candidate's profile and report how deeply it shows the candidate has used a skill.

You get numbered PASSAGES copied from the candidate's profile and numbered SKILLS. For every skill report the ONE depth that the passages demonstrate for that skill:
- "unspecified": the passages do not demonstrate real use of the skill. It is absent, or only named (a skills list, a job title, a headline, years of experience with no
  description of the work), or only studied, read about or described as "familiar" without use in real work.
- "working_knowledge": the passages show real but modest or supporting use: the candidate has used the skill in real work for ordinary tasks, or states working knowledge
  of it, without owning complex work built on it.
- "hands_on": the passages show the candidate personally building, writing, configuring or operating with the skill as a core part of their real work.
- "advanced": the passages state expertise, or show sophisticated work built with the skill: complex design, optimisation, architecture, or mastery of its advanced features.

Rules:
1. Report what the evidence DEMONSTRATES, not what the skill name suggests. Never infer a depth from a job title, from generic verbs ("worked on", "responsible for",
   "involved in"), from years of experience, from a list of skills, or from the employer.
2. Judge each skill only from passages about THAT skill. Evidence for another skill is not evidence for this one.
3. For any depth other than "unspecified" you MUST give the passage number and a quote copied EXACTLY, character for character, from that ONE passage: one contiguous span of
   at most 220 characters, no ellipsis ("..." or "\u2026"), no paraphrase. The quote must itself name the skill and show the depth.
4. If you cannot give such a quote, answer "unspecified".
5. If several passages differ, report the deepest depth that has a valid quote.

For every skill also report the evidence_basis: what KIND of evidence the quote is.
- "explicit_depth": the quote itself states a proficiency level for the skill (for example "advanced", "expert", "hands-on", "working knowledge").
- "concrete_skill_use": the quote describes the candidate actually building, creating, operating, implementing, analysing or performing work directly with the skill.
- "routine_skill_use": the quote describes ordinary, repeated or basic use of the skill.
- "generic_involvement": the quote says the candidate worked on, took part in, was involved with or was responsible for something that involves the skill, without describing concrete use of the skill and without stating a depth.
- "no_depth_evidence": the skill is only listed, appears in a title, or is otherwise not demonstrated.

Return only JSON: {"results":[{"d":<skill number>,"observed_depth":"unspecified|working_knowledge|hands_on|advanced","evidence_basis":"explicit_depth|concrete_skill_use|routine_skill_use|generic_involvement|no_depth_evidence","p":<passage number or null>,"quote":"<exact quote or empty>"}]}
Include every skill exactly once."""


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
    # What the Judge was GIVEN (backend/services/consumer_input): where the requirements came from ("compiled" | "legacy"), the per-path checklist with
    # its exclusions, preferences, unresolved items and provenance, and every legacy value that disagreed with the compiled meaning (the compiled one was used).
    input_source: str = "legacy"
    checklist: Optional[Dict[str, Any]] = None
    disagreements: Optional[List[Dict[str, Any]]] = None
    # The semantic exclusions evaluated against the profile, one entry per negative Evidence Check: state PRESENT | NOT_PRESENT | INSUFFICIENT_EVIDENCE, the
    # check_id it is bound to, and, for PRESENT, a quote that passed the quote gate and the indicator binding. None = nothing to evaluate / not evaluated.
    exclusion_judgments: Optional[List[Dict[str, Any]]] = None
    exclusion_failed: bool = False
    # The Evidence Checks (positive and negative) every verdict is bound to, the one narrow quote retry, and every verdict the deterministic binding discarded.
    checks: Optional[List[Dict[str, Any]]] = None
    retries: Dict[str, List[Dict[str, Any]]] = field(default_factory=lambda: {"requirement": [], "exclusion": []})
    binding_discards: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.input_tokens * INPUT_USD_PER_MILLION_TOKENS + self.output_tokens * OUTPUT_USD_PER_MILLION_TOKENS
        ) / 1_000_000


# the instruction added to the payload of the ONE retry (only the checks whose quote failed verification are re-asked)
_RETRY_INSTRUCTION = (
    "RETRY of the checks below only. Your previous quote for each could not be verified: it was not one contiguous span copied character for character from ONE passage "
    "(for example it contained an ellipsis, '...' or the single character, it joined two places, or it was paraphrased). Answer again. Copy ONE contiguous span exactly, "
    "with no ellipsis and no changes. If no such span exists, do not claim the check."
)


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
        outcome = self._judge_requirements(candidate, intent, harvest_evidence)
        consumer_input = resolve_consumer_input(intent)
        if consumer_input.checklist is not None and consumer_input.checklist.exclusions and not outcome.failed:
            self._evaluate_exclusions(candidate, intent, harvest_evidence, consumer_input.checklist, outcome)
        return outcome

    # ------------------------------------------------------------------------------------------------------ negatives

    def _evaluate_exclusions(
        self, candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence], checklist: Any, outcome: JudgeOutcome
    ) -> None:
        """The negatives: each exclusion is an explicit predicate (a negative Evidence Check), answered PRESENT / NOT_PRESENT / INSUFFICIENT_EVIDENCE. One call per
        candidate (plus at most ONE retry of only the checks whose quote failed verification), never for an intent without exclusions.

          PRESENT only with a quote that passes the quote gate (one contiguous, exact, ellipsis-free span of ONE passage) AND contains an indicator of the
          predicate itself. A PRESENT claim that cannot be so evidenced is INSUFFICIENT_EVIDENCE, never NOT_PRESENT.
          NOT_PRESENT needs a profile that actually describes work (demonstrated work or a certification); without one it is INSUFFICIENT_EVIDENCE.
        A failure here never touches the requirement judgments."""
        try:
            negatives = negative_checks(checklist)
            outcome.checks = (outcome.checks or []) + [c.to_dict() for c in negatives]
            passages = build_passages(candidate, intent, harvest_evidence)
            has_work = any(p.evidence_type in WORK_EVIDENCE_TYPES for p in passages)
            client = self._client or OpenAI(api_key=get_openai_api_key()) if passages else None
            rows: Dict[int, Dict[str, Any]] = {}
            if passages:
                rows = self._ask_exclusions(client, passages, [(i, c) for i, c in enumerate(negatives)], outcome, retry=False)

            def resolve_row(i: int, c: EvidenceCheck, row: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any], Optional[str]]:
                """(state, evidence fields, failure) for one check from one model row. `failure` is a RETRIABLE quote failure when a PRESENT claim must be re-asked."""
                if not passages:
                    return INSUFFICIENT_EVIDENCE, {"reason": "no profile text to evaluate"}, None
                if row is None:
                    return INSUFFICIENT_EVIDENCE, {"reason": "the model gave no answer for this check"}, None
                verdict = str(row.get("verdict") or "").strip().casefold()
                if verdict == "present":
                    quote = str(row.get("quote") or "").strip()
                    try:
                        pi = int(row.get("p"))
                        passage = passages[pi] if pi >= 0 else None
                    except (TypeError, ValueError, IndexError):
                        passage = None
                    ok, why = verify_quote(quote, passage.text if passage is not None else None)
                    if not ok:
                        return INSUFFICIENT_EVIDENCE, {"reason": f"present_claim_unverified:{why}", "discarded_quote": quote[:240]}, why
                    bind = validate_binding(c, quote, passage.evidence_type, passage.label)
                    if bind:
                        outcome.binding_discards.append({"check_id": c.check_id, "reason": bind, "quote": quote[:240]})
                        return INSUFFICIENT_EVIDENCE, {"reason": f"present_claim_not_supported:{bind}", "discarded_quote": quote[:240]}, None
                    return PRESENT, {"quote": quote, "source": passage.label, "evidence_detail": passage.detail, "reason": "model, quote verified and bound"}, None
                if verdict == "not_present":
                    if not has_work:
                        return INSUFFICIENT_EVIDENCE, {"reason": "floor: the profile contains no description of work, so the exclusion cannot be cleared"}, None
                    return NOT_PRESENT, {"reason": "model"}, None
                if verdict == "insufficient_evidence":
                    return INSUFFICIENT_EVIDENCE, {"reason": "model"}, None
                return INSUFFICIENT_EVIDENCE, {"reason": f"unrecognised verdict {verdict!r}"}, None

            resolved = {i: resolve_row(i, c, rows.get(i)) for i, c in enumerate(negatives)}
            retry = [i for i, (_st, _ev, failure) in resolved.items() if failure in RETRIABLE_QUOTE_FAILURES]
            if retry and passages:
                second = self._ask_exclusions(client, passages, [(i, negatives[i]) for i in retry], outcome, retry=True)
                for i in retry:
                    first_failure = resolved[i][2]
                    new = resolve_row(i, negatives[i], second.get(i))
                    outcome.retries["exclusion"].append({"check_id": negatives[i].check_id, "first_pass_failure": first_failure, "recovered": new[2] is None, "final_failure": new[2],
                                                         "final_state": new[0] if new[2] is None else INSUFFICIENT_EVIDENCE})
                    resolved[i] = (new[0], new[1], None) if new[2] is None else (INSUFFICIENT_EVIDENCE, {**new[1], "reason": f"present_claim_unverified_after_retry:{new[2]}"}, None)
            judged: List[Dict[str, Any]] = []
            for i, c in enumerate(negatives):
                state, ev, _f = resolved[i]
                judged.append({"check_id": c.check_id, "text": c.label, "item_id": c.check_id.split("#", 1)[-1].rsplit("|", 1)[0], "path_id": c.path_id, "provenance": dict(c.provenance),
                               "verdict": state, "state": state, **ev})
            outcome.exclusion_judgments = judged
        except Exception:  # noqa: BLE001 - an exclusion failure must never break a search or the requirement judgments
            logger.warning("Exclusion evaluation failed | candidate_id=%s", candidate.candidate_id, exc_info=True)
            outcome.exclusion_failed = True
            outcome.exclusion_judgments = None

    def _ask_exclusions(self, client: Any, passages: List[TextSource], numbered: List[Tuple[int, EvidenceCheck]], outcome: JudgeOutcome, retry: bool) -> Dict[int, Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "passages": [{"p": i, "label": p.label, "text": (p.text or "")[:MAX_PASSAGE_CHARS]} for i, p in enumerate(passages)],
            "exclusion_checks": [{"x": i, "predicate": model_predicate(c.predicate)} for i, c in numbered],
        }
        if retry:
            payload["instruction"] = _RETRY_INSTRUCTION
        response = client.responses.create(
            model=self._model,
            input=[{"role": "system", "content": _EXCLUSION_PROMPT}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            text={"format": {"type": "json_object"}},
            temperature=0,
        )
        outcome.calls += 1
        usage = getattr(response, "usage", None)
        outcome.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        outcome.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        content = getattr(response, "output_text", None)
        if not content:
            raise ValueError("empty exclusion response")
        wanted = {i for i, _ in numbered}
        seen: Dict[int, List[Dict[str, Any]]] = {}
        for r in json.loads(content).get("results", []):
            if isinstance(r, dict) and "x" in r:
                try:
                    x = int(r["x"])
                except (TypeError, ValueError):
                    continue
                if x in wanted:
                    seen.setdefault(x, []).append(r)
        # a verdict binds to exactly ONE check: an id answered twice is ambiguous and is treated as unanswered
        return {x: rs[0] for x, rs in seen.items() if len(rs) == 1}

    # ------------------------------------------------------------------------------------------------------ positives

    def _judge_requirements(
        self, candidate: Candidate, intent: SearchIntent, harvest_evidence: Optional[HarvestEvidence]
    ) -> JudgeOutcome:
        consumer_input = resolve_consumer_input(intent)
        requirements = list(consumer_input.judged)
        header = dict(
            input_source=consumer_input.source,
            checklist=consumer_input.checklist.to_dict() if consumer_input.checklist is not None else None,
            disagreements=[d.to_dict() for d in consumer_input.disagreements] if consumer_input.source == "compiled" else None,
        )
        if not requirements:
            return JudgeOutcome(judgments=None, **header)
        checks = positive_checks(consumer_input)                    # one Evidence Check per requirement, aligned by index
        outcome = JudgeOutcome(judgments=None, requirements=len(requirements), checks=[c.to_dict() for c in checks], **header)
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
                    deterministic[i]["check_id"] = checks[i].check_id
            remaining = [i for i in range(len(requirements)) if i not in deterministic]

            if not remaining:
                outcome.judgments = [deterministic[i] for i in range(len(requirements))]
                return outcome

            passages = build_passages(candidate, intent, harvest_evidence)
            if not passages:
                outcome.judgments = [
                    deterministic[i] if i in deterministic else self._not_evidenced(checks[i])
                    for i in range(len(requirements))
                ]
                return outcome

            client = self._client or OpenAI(api_key=get_openai_api_key())
            # Two families of checks. A DEPTH check (skill + required depth) is not asked "does the evidence meet the depth"; the model reports the depth the evidence
            # DEMONSTRATES (`observed_depth`) and CODE compares it with the required depth. Every other check is asked as before.
            depth_idx = [i for i in remaining if checks[i].proficiency and checks[i].subject]
            plain_idx = [i for i in remaining if i not in set(depth_idx)]

            def collect(indices: List[int], ask) -> Optional[Dict[int, Dict[str, Any]]]:
                # The model sometimes answers only some of the requirements (seen
                # live: 3 of 12 on one call, 12 of 12 on the next, same input).
                # A silently missing answer would read as "not evidenced" and
                # randomly under-rank a candidate, so ask again for just the
                # missing ones, once.
                got: Dict[int, Dict[str, Any]] = {}
                pending = list(indices)
                for attempt in range(2):
                    if not pending:
                        break
                    answered = ask(pending)
                    if answered is None:
                        return None
                    got.update(answered)
                    pending = [i for i in pending if i not in got]
                    if pending and attempt == 0:
                        outcome.re_asked_missing += len(pending)
                return got

            ask_plain = lambda pend, retry=False: self._ask(client, passages, [(i, checks[i].criterion) for i in pend], outcome, retry=retry)           # noqa: E731
            ask_depth = lambda pend, retry=False: self._ask_depth(client, passages, [(i, checks[i]) for i in pend], outcome, retry=retry)                # noqa: E731
            verified: Dict[int, Tuple[Dict[str, Any], Optional[str]]] = {}
            for indices, ask, verify in ((plain_idx, ask_plain, self._verify_check), (depth_idx, ask_depth, self._verify_depth)):
                if not indices:
                    continue
                got = collect(indices, ask)
                if got is None:
                    outcome.failed = True
                    return outcome
                for i in indices:
                    verified[i] = verify(checks[i], got.get(i), passages, outcome)
                # THE narrow retry: only the checks whose quote failed verification (never a check that succeeded, never a binding discard), once, with an exact-quote
                # instruction. The verifier is the same; it is not relaxed.
                retry = [i for i in indices if verified[i][1] in RETRIABLE_QUOTE_FAILURES]
                if retry:
                    second = ask(retry, retry=True)
                    for i in retry:
                        first_failure = verified[i][1]
                        again = verify(checks[i], (second or {}).get(i), passages, outcome) if second is not None else verified[i]
                        recovered = again[0].get("verdict") in ("met", "partly")
                        outcome.retries["requirement"].append({"check_id": checks[i].check_id, "first_pass_failure": first_failure, "recovered": recovered,
                                                               "final_failure": None if recovered else (again[1] or "not_claimed")})
                        verified[i] = again
            outcome.judgments = [deterministic[i] if i in deterministic else verified[i][0] for i in range(len(requirements))]
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
        and the failure is recorded.

        The reviewer is given the Evidence Check's COMPLETE claim (`criterion`: for a depth claim, the skill AND the depth), not a label."""
        claims = [
            (index, judgment)
            for index, judgment in enumerate(outcome.judgments or [])
            if judgment.get("verdict") == "met" and judgment.get("source") != "career dates" and not judgment.get("deterministic") and "observed_depth" not in judgment
        ]
        if not claims:
            return

        def review_one(index: int, judgment: Dict[str, Any]) -> tuple:
            try:
                response = client.responses.create(
                    model=self._model,
                    input=[
                        {"role": "system", "content": _REVIEW_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"claims": [{"i": index, "requirement": judgment.get("criterion") or judgment["signal_text"], "quote": judgment["quote"]}]},
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    text={"format": {"type": "json_object"}},
                    temperature=0,
                )
                usage = getattr(response, "usage", None)
                reviewed = json.loads(getattr(response, "output_text", "") or "{}").get("results", [])
                supported = any(
                    isinstance(r, dict) and r.get("i") == index and bool(r.get("supports")) for r in reviewed
                )
                return index, supported, None, usage
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
        self, client: Any, passages: List[TextSource], numbered: List[tuple], outcome: "JudgeOutcome", retry: bool = False
    ) -> Optional[Dict[int, Dict[str, Any]]]:
        payload: Dict[str, Any] = {
            "passages": [
                {"p": i, "label": p.label, "text": (p.text or "")[:MAX_PASSAGE_CHARS]} for i, p in enumerate(passages)
            ],
            "requirements": [{"r": index, "text": text} for index, text in numbered],
        }
        if retry:
            payload["instruction"] = _RETRY_INSTRUCTION
        response = client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            text={"format": {"type": "json_object"}},
            temperature=0,
        )
        outcome.calls += 1
        usage = getattr(response, "usage", None)
        outcome.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        outcome.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        content = getattr(response, "output_text", None)
        if not content:
            return None
        wanted = {index for index, _ in numbered}
        seen: Dict[int, List[Dict[str, Any]]] = {}
        for r in json.loads(content).get("results", []):
            if isinstance(r, dict) and "r" in r and int(r["r"]) in wanted:
                seen.setdefault(int(r["r"]), []).append(r)
        # a verdict binds to exactly ONE check: an id answered twice is ambiguous and is treated as unanswered (so it is re-asked, not guessed)
        return {i: rs[0] for i, rs in seen.items() if len(rs) == 1}

    def _ask_depth(
        self, client: Any, passages: List[TextSource], numbered: List[Tuple[int, EvidenceCheck]], outcome: "JudgeOutcome", retry: bool = False
    ) -> Optional[Dict[int, Dict[str, Any]]]:
        """The depth pass: for each skill the model reports the depth the passages DEMONSTRATE. It is never told the depth the check requires."""
        payload: Dict[str, Any] = {
            "passages": [{"p": i, "label": p.label, "text": (p.text or "")[:MAX_PASSAGE_CHARS]} for i, p in enumerate(passages)],
            "skills": [{"d": i, "skill": c.subject} for i, c in numbered],
        }
        if retry:
            payload["instruction"] = _RETRY_INSTRUCTION
        response = client.responses.create(
            model=self._model,
            input=[{"role": "system", "content": _DEPTH_PROMPT}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            text={"format": {"type": "json_object"}},
            temperature=0,
        )
        outcome.calls += 1
        usage = getattr(response, "usage", None)
        outcome.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        outcome.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        content = getattr(response, "output_text", None)
        if not content:
            return None
        wanted = {i for i, _ in numbered}
        seen: Dict[int, List[Dict[str, Any]]] = {}
        for r in json.loads(content).get("results", []):
            if isinstance(r, dict) and "d" in r:
                try:
                    d = int(r["d"])
                except (TypeError, ValueError):
                    continue
                if d in wanted:
                    seen.setdefault(d, []).append(r)
        return {d: rs[0] for d, rs in seen.items() if len(rs) == 1}

    def _verify_depth(
        self, check: EvidenceCheck, row: Optional[Dict[str, Any]], passages: List[TextSource], outcome: JudgeOutcome
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """(judgment, failure) for a depth check. The model's `observed_depth` is accepted only with a quote that passes the quote gate and supports THIS skill from
        demonstrated work or a certification (a title, headline, skills-list entry or computed passage is never depth evidence); otherwise the observation is
        `unspecified` and the reason is kept. The verdict is then CODE: `met` iff observed >= required on unspecified < working_knowledge < hands_on < advanced; below the
        requirement but demonstrated is `partly`; undemonstrated is `not_evidenced`."""
        required = check.proficiency
        base = {"tier": check.tier, "signal_text": check.label, "check_id": check.check_id, "criterion": check.criterion, "verdict": "not_evidenced",
                "observed_depth": "unspecified", "required_depth": required, "claimed_depth": None, "evidence_basis": None, "maximum_supported_depth": "unspecified",
                "capped": False}
        if not row:
            return base, None
        claimed = str(row.get("observed_depth") or "").strip().casefold().replace("-", "_").replace(" ", "_")
        basis = str(row.get("evidence_basis") or "").strip().casefold().replace("-", "_").replace(" ", "_")
        basis = basis if basis in EVIDENCE_BASES else None
        base.update(evidence_basis=basis)
        if claimed not in OBSERVED_DEPTHS:
            base.update(claimed_depth=claimed or None, discard_reason="unrecognised_observed_depth")
            return base, None
        base["claimed_depth"] = claimed
        if claimed == "unspecified":
            return base, None
        if basis is None:
            # no recognised evidence basis: nothing is supported, so the claim cannot be credited (never silently passes)
            base.update(discard_reason="missing_evidence_basis", capped=True)
            return base, None
        quote = str(row.get("quote") or "").strip()
        try:
            pi = int(row.get("p"))
            passage = passages[pi] if pi >= 0 else None
        except (TypeError, ValueError, IndexError):
            passage = None
        ok, why = verify_quote(quote, passage.text if passage is not None else None)
        if not ok:
            base.update(discard_reason=why, discarded_quote=quote[:240])
            return base, why
        bind = validate_binding(check, quote, passage.evidence_type, passage.label)
        if bind:
            base.update(discard_reason=bind, discarded_quote=quote[:240])
            outcome.binding_discards.append({"check_id": check.check_id, "reason": bind, "quote": quote[:240]})
            return base, bind
        # the CEILING: the deepest depth the cited evidence can support, decided by code from the evidence basis. The model can never raise the depth above it.
        ceiling = maximum_supported_depth(basis, quote, check.subject_terms)
        effective = effective_depth(claimed, ceiling)
        base.update(maximum_supported_depth=ceiling, capped=DEPTH_ORDER[effective] < DEPTH_ORDER[claimed])
        if effective == "unspecified":
            base.update(discard_reason="evidence_basis_supports_no_depth", discarded_quote=quote[:240])
            return base, None
        met = meets_depth(effective, required)
        base.update(verdict="met" if met else "partly", observed_depth=effective, quote=quote, term=check.subject, source=passage.label, evidence_detail=passage.detail,
                    evidence_type=passage.evidence_type, strength=passage.strength,
                    depth_rule="effective_depth = min(claimed, ceiling(evidence_basis)); effective_depth >= required_depth (unspecified < working_knowledge < hands_on < advanced)")
        return base, None

    @staticmethod
    def _not_evidenced(check: EvidenceCheck) -> Dict[str, Any]:
        return {"tier": check.tier, "signal_text": check.label, "verdict": "not_evidenced", "check_id": check.check_id, "criterion": check.criterion}

    def _verify_check(
        self, check: EvidenceCheck, result: Optional[Dict[str, Any]], passages: List[TextSource], outcome: JudgeOutcome
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """(judgment, failure). A `met` / `partly` verdict stands only if (1) its quote passes the quote gate (contiguous, exact, no ellipsis, ONE passage) and (2) the
        quote supports THIS check (deterministic binding: the skill's own name, demonstrated work for a depth claim). `failure` is the reason a claimed verdict was
        discarded: a RETRIABLE quote failure is re-asked once; a binding failure is final."""
        base = self._not_evidenced(check)
        if not result or result.get("verdict") not in ("met", "partly"):
            return base, None
        quote = str(result.get("quote") or "").strip()
        try:
            pi = int(result.get("p"))
            passage = passages[pi] if pi >= 0 else None
        except (TypeError, ValueError, IndexError):
            passage = None
        ok, why = verify_quote(quote, passage.text if passage is not None else None)
        if not ok:
            logger.info("Discarded unverified quote (%s) for check %s", why, check.check_id)
            base.update(discard_reason=why, discarded_quote=quote[:240])
            return base, why
        bind = validate_binding(check, quote, passage.evidence_type, passage.label)
        if bind:
            logger.info("Discarded a quote that does not support check %s (%s)", check.check_id, bind)
            base.update(discard_reason=bind, discarded_quote=quote[:240])
            outcome.binding_discards.append({"check_id": check.check_id, "reason": bind, "quote": quote[:240]})
            return base, bind
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
            "tier": check.tier,
            "signal_text": check.label,
            "check_id": check.check_id,
            "criterion": check.criterion,
            "verdict": result["verdict"],
            "quote": quote,
            "term": term,
            "source": passage.label,
            "evidence_detail": detail,
            "evidence_type": passage.evidence_type,
            "strength": passage.strength,
        }, None
