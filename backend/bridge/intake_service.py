"""IntakeService — the new 7-agent brain behind the frontend's intake/search
contract. Wraps `recruiter.pipeline` + file-JSON session storage, and returns the
dayzero.partners shapes via `translate`.

Design mirrors the legacy semantics the frontend relies on:
  * the reader (LLM) runs ONCE at `start`; `answer` and `update_boundary` only
    re-run the pure `assemble` over the cached Understanding (no model call), the
    same "deterministic, no model call" guarantee the legacy boundary edit made.
  * `confirm` builds the immutable confirmed RoleModel (content-hashed id) that
    `run_search` is the only thing allowed to execute.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.bridge.session_store import ConfirmationStore
from backend.bridge.translate import (
    to_intake_result,
    to_intake_result_pending,
    to_intake_result_reading,
    to_running_search_response,
    to_search_intent,
    to_search_intent_from_understanding,
    to_search_response,
)
from recruiter.agents.calibration.apply import apply_answers
from recruiter.role_model.serde import to_dict

_ROOT = Path(__file__).resolve().parents[2] / "output"


class ConfirmationNotReady(ValueError):
    def __init__(self, reasons: List[str]) -> None:
        super().__init__("; ".join(reasons) or "The brief is not ready to search.")
        self.reasons = reasons


class IntakeReadError(RuntimeError):
    """The background role read (the LLM) failed for this session — the caller
    should surface a recruiter-friendly error on the poll."""


def _session_store():
    # A DEDICATED dir — must NOT collide with the legacy intake_session_manager's
    # output/intake_sessions: new-engine sessions carry fields (understanding,
    # include_companies) that the legacy SearchBoundary loader can't reconstruct.
    from backend.services.search_store import SearchStore
    return SearchStore(storage_dir=_ROOT / "engine_intake_sessions")


def _u_to_dict(u) -> Dict[str, Any]:
    return dataclasses.asdict(u)


def _u_from_dict(d: Dict[str, Any]):
    from recruiter.agents.intake.model import ReadRequirement, Understanding
    return Understanding(
        identity=d["identity"],
        requirements=tuple(ReadRequirement(r["text"], r["tier"], r.get("evidence"), r.get("when", "any"))
                           for r in (d.get("requirements") or ())),
        posted_title=d.get("posted_title"), posted_title_source=d.get("posted_title_source"),
        min_years=d.get("min_years"), max_years=d.get("max_years"),
        employment_type=d.get("employment_type"), work_mode_in_notes=d.get("work_mode_in_notes"),
    )


def _content_id(model_dict: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(model_dict, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _coerce_answer(issue_id: str, value: Any) -> Any:
    if issue_id in ("min_years", "max_years"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if issue_id == "retier":
        # The editable-brief tier map ({requirement_text: tier}) arrives as a JSON
        # string (the /answer value field is a str). Decode to the dict apply_answers
        # expects; a malformed map is dropped rather than poisoning the brief.
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return value


class IntakeService:
    def __init__(self, pipeline, sessions=None, confirmations: Optional[ConfirmationStore] = None) -> None:
        self._pipe = pipeline
        self._sessions = sessions or _session_store()
        self._confirmations = confirmations or ConfirmationStore()

    # --- internals ---
    def _result_from(self, raw_input, understanding, boundary, answers) -> Dict[str, Any]:
        outcome = self._pipe.intake.assemble(understanding, boundary, answers)
        if not outcome.ready:
            # Tier edits are allowed while another required clarification is
            # still open. Keep those edits visible in the pending brief too.
            retier = answers.get("retier") or {}
            pending_understanding = understanding
            if isinstance(retier, dict) and retier:
                pending_understanding = dataclasses.replace(
                    understanding,
                    requirements=tuple(
                        dataclasses.replace(requirement, tier=retier.get(requirement.text, requirement.tier))
                        for requirement in understanding.requirements
                    ),
                )
            return to_intake_result_pending(raw_input, pending_understanding, outcome.clarifications)
        # Apply the recruiter's refinement answers so the brief reflects them LIVE
        # (e.g. capability 'remove' drops it from Core and widens the search; a
        # dealbreaker is marked hard) — the same apply confirm/search will use.
        model = apply_answers(outcome.model, answers or {}, outcome.refinements)
        # Refinements are stateless (regenerated every assemble), so drop the ones
        # the recruiter already answered — otherwise the decision card never clears
        # and Search stays locked (the frontend gates on pending 'ask' issues).
        answered = set(answers or {})
        pending = tuple(q for q in outcome.refinements if q.id not in answered)
        return to_intake_result(raw_input, model, pending, "ready")

    def _save(self, session_id, raw_input, understanding, boundary, answers, posted_title) -> None:
        self._sessions.save(session_id, {
            "session_id": session_id, "raw_input": raw_input,
            "understanding": _u_to_dict(understanding), "boundary": boundary or {},
            "answers": answers or {}, "posted_title": posted_title,
        })

    def _seed_answers(self, boundary) -> Dict[str, Any]:
        """Min/max years are now first-step recruiter inputs (on the boundary), so
        seed them as answers — authoritative, and they stop the missing-years
        clarification from ever firing."""
        answers: Dict[str, Any] = {}
        b = boundary or {}
        for key in ("min_years", "max_years"):
            if b.get(key) not in (None, ""):
                try:
                    answers[key] = int(b[key])
                except (TypeError, ValueError):
                    pass
        return answers

    def _require(self, session_id) -> Dict[str, Any]:
        rec = self._sessions.load(session_id)
        if rec is None or not rec.get("understanding"):
            raise KeyError(session_id)
        return rec

    # --- API ---
    def parse_jd(self, jd_text: str) -> Dict[str, Any]:
        return to_search_intent_from_understanding(self._pipe.intake.read(jd_text, None))

    def start(self, raw_input: str, boundary: Dict[str, Any], posted_title: Optional[str] = None) -> Dict[str, Any]:
        """Synchronous read + assemble (used by tests and as a fallback). The HTTP
        path uses begin()+read_into() so the ~30s read never blocks the request."""
        u = self._pipe.intake.read(raw_input, posted_title or (boundary or {}).get("posted_title"))
        session_id = str(uuid4())
        answers = self._seed_answers(boundary)
        result = self._result_from(raw_input, u, boundary or {}, answers)
        self._save(session_id, raw_input, u, boundary or {}, answers, posted_title)
        return {"session_id": session_id, "result": result, "boundary": boundary or {}}

    def begin(self, raw_input: str, boundary: Dict[str, Any], posted_title: Optional[str] = None) -> Dict[str, Any]:
        """Allocate a session and mark it 'reading' WITHOUT running the LLM — the
        caller then runs read_into(session_id) on a background thread. Returns the
        'understanding' placeholder brief the frontend polls on."""
        session_id = str(uuid4())
        self._sessions.save(session_id, {
            "session_id": session_id, "raw_input": raw_input, "understanding": None,
            "boundary": boundary or {}, "answers": self._seed_answers(boundary),
            "posted_title": posted_title, "reading": True,
        })
        return {"session_id": session_id, "result": to_intake_result_reading(raw_input),
                "boundary": boundary or {}}

    def read_into(self, session_id: str) -> None:
        """Run the LLM read for a session begun with begin() and store the full
        brief. On failure, mark the session so get() raises IntakeReadError."""
        rec = self._sessions.load(session_id)
        if rec is None:
            return
        try:
            u = self._pipe.intake.read(
                rec["raw_input"],
                rec.get("posted_title") or (rec.get("boundary") or {}).get("posted_title"))
        except Exception:
            cur = self._sessions.load(session_id) or rec
            cur["reading"] = False
            cur["read_error"] = True
            self._sessions.save(session_id, cur)
            raise
        self._save(session_id, rec["raw_input"], u, rec.get("boundary") or {},
                   dict(rec.get("answers") or {}), rec.get("posted_title"))

    def answer(self, session_id: str, issue_id: str, value: Any, label: str = "") -> Dict[str, Any]:
        rec = self._require(session_id)
        u = _u_from_dict(rec["understanding"])
        answers = dict(rec.get("answers") or {})
        answers[issue_id] = _coerce_answer(issue_id, value)
        result = self._result_from(rec["raw_input"], u, rec.get("boundary") or {}, answers)
        self._save(session_id, rec["raw_input"], u, rec.get("boundary") or {}, answers, rec.get("posted_title"))
        return {"session_id": session_id, "result": result}

    def update_boundary(self, session_id: str, boundary: Dict[str, Any]) -> Dict[str, Any]:
        rec = self._require(session_id)
        u = _u_from_dict(rec["understanding"])
        answers = dict(rec.get("answers") or {})
        answers.update(self._seed_answers(boundary))   # boundary years override
        result = self._result_from(rec["raw_input"], u, boundary or {}, answers)
        self._save(session_id, rec["raw_input"], u, boundary or {}, answers, rec.get("posted_title"))
        return {"session_id": session_id, "result": result, "boundary": boundary or {}}

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        rec = self._sessions.load(session_id)
        if rec is None:
            return None
        if rec.get("read_error"):
            raise IntakeReadError(session_id)
        if not rec.get("understanding"):
            # Still reading on the background thread — hand back the placeholder so
            # the frontend keeps polling (None would 404 and look like a lost session).
            if rec.get("reading"):
                return {"session_id": session_id, "result": to_intake_result_reading(rec.get("raw_input", "")),
                        "boundary": rec.get("boundary") or {}, "posted_title_input": rec.get("posted_title")}
            return None
        u = _u_from_dict(rec["understanding"])
        result = self._result_from(rec["raw_input"], u, rec.get("boundary") or {}, rec.get("answers") or {})
        return {"session_id": session_id, "result": result, "boundary": rec.get("boundary") or {},
                "posted_title_input": rec.get("posted_title")}

    def confirm(self, session_id: str, edits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rec = self._require(session_id)
        u = _u_from_dict(rec["understanding"])
        answers = dict(rec.get("answers") or {})
        outcome = self._pipe.intake.assemble(u, rec.get("boundary") or {}, answers)
        if not outcome.ready:
            raise ConfirmationNotReady([q.prompt for q in outcome.clarifications])
        model = apply_answers(outcome.model, {**answers, **(edits or {})}, outcome.refinements)
        model = dataclasses.replace(model, model_id=_content_id(to_dict(model)))
        self._confirmations.create(model)
        return {"confirmation_id": model.model_id, "session_id": session_id,
                "posted_title": model.posted_title, "posted_title_source": model.posted_title_source,
                "candidate_identity": model.identity, "content_hash": model.model_id,
                "search_intent": to_search_intent(model), "edits": edits or {}}

    def search_intent_preview(self, session_id: str) -> Dict[str, Any]:
        """What /intake/{id}/confirm returns: the SearchIntent for the current
        (ready) brief, WITHOUT creating a snapshot — the frontend fires this to
        render 'this is what I will search for'. 409 if still missing years."""
        rec = self._require(session_id)
        u = _u_from_dict(rec["understanding"])
        outcome = self._pipe.intake.assemble(u, rec.get("boundary") or {}, rec.get("answers") or {})
        if not outcome.ready:
            raise ConfirmationNotReady([q.prompt for q in outcome.clarifications])
        return to_search_intent(outcome.model)

    @staticmethod
    def _feedback_screen_context(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Small, structured recruiter examples for the cheap relevance screen.

        Free-text notes are deliberately excluded. The screen sees only profile
        summaries and explicit shortlist/maybe/reject decisions with reason codes.
        """
        if not record:
            return {}
        from backend.services.role_lifecycle import initial_validation_ids
        first_ids = initial_validation_ids(record)
        decisions = record.get("recruiter_decisions") or {}
        if first_ids and any(decisions.get(candidate_id) not in ("shortlist", "maybe", "reject")
                             for candidate_id in first_ids):
            return {}
        response = record.get("response") or {}
        candidates = response.get("candidates") or []
        explanations = response.get("explanations") or []
        evidence_rows = response.get("evidence") or []
        by_id = {candidate.get("candidate_id"): i for i, candidate in enumerate(candidates)
                 if candidate.get("candidate_id")}
        events = {}
        for event in record.get("feedback_events") or []:
            events[event.get("candidate_id")] = event

        def example(candidate_id: str, decision: str) -> Optional[Dict[str, Any]]:
            index = by_id.get(candidate_id)
            if index is None:
                return None
            candidate = candidates[index]
            explanation = explanations[index] if index < len(explanations) else {}
            evidence = evidence_rows[index] if index < len(evidence_rows) else {}
            alignment = evidence.get("role_alignment") or {}
            core_signals = [
                {"signal": row.get("signal_text"), "verdict": row.get("verdict")}
                for row in (evidence.get("requirement_judgments") or [])
                if row.get("tier") == "core" and row.get("signal_text")
            ][:4]
            event = events.get(candidate_id) or {}
            item = {
                "decision": decision,
                "title": candidate.get("title"),
                "experience_years": candidate.get("experience_years"),
                "location": candidate.get("location"),
                "role_evidence": (explanation.get("why_this_candidate") or "")[:160],
                "core_signals": core_signals,
                "level_fit": alignment.get("level_fit"),
                "experience_floor": alignment.get("experience_floor"),
            }
            if event.get("feedback_reason"):
                item["reason"] = event["feedback_reason"]
            return item

        context = {"shortlisted": [], "maybe": [], "rejected": []}
        for candidate_id, decision in decisions.items():
            if decision not in ("shortlist", "maybe", "reject"):
                continue
            item = example(candidate_id, decision)
            if item is None:
                continue
            bucket = "shortlisted" if decision == "shortlist" else "maybe" if decision == "maybe" else "rejected"
            context[bucket].append(item)
        return {key: values[-5:] for key, values in context.items()}

    def run_search(self, confirmation_id: str, search_id: str, provider: str = "crustdata",
                   on_progress: Optional[Any] = None, cursor: Optional[str] = None,
                   feedback_record: Optional[Dict[str, Any]] = None,
                   admit_all_relevant: bool = False, surface_all: bool = False) -> Dict[str, Any]:
        model = self._confirmations.load(confirmation_id)
        if model is None:
            raise KeyError(confirmation_id)
        plan = self._pipe.briefing.build(model)
        search_result = self._pipe.search.run(plan.query, cursor=cursor)
        candidates = list(search_result.candidates)
        # Stream progress while the slow per-candidate Judge loop runs: the caller's
        # on_progress sink persists each snapshot so GET /search/{id} shows movement.
        rank_progress = None
        if on_progress is not None:
            on_progress(to_running_search_response(
                provider, search_id, pulled=search_result.pulled, kept=len(candidates)))

            def rank_progress(admitted: int, processed: int) -> None:
                on_progress(to_running_search_response(
                    provider, search_id, pulled=search_result.pulled, kept=len(candidates),
                    admitted=admitted, processed=processed))
        feedback_context = self._feedback_screen_context(feedback_record)
        ranking = self._pipe.ranking.rank(
            model, candidates, on_progress=rank_progress,
            admit_all_relevant=admit_all_relevant, feedback_context=feedback_context,
        )
        resp = to_search_response(provider, search_id, model, search_result, ranking,
                                  surface_all=surface_all)
        resp["confirmed_brief"] = {
            "confirmation_id": confirmation_id, "session_id": "",
            "posted_title": model.posted_title, "posted_title_source": model.posted_title_source,
            "candidate_identity": model.identity, "content_hash": confirmation_id,
        }
        return resp

    def analyze_reserve(self, confirmation_id: str, entries: List[Dict[str, Any]],
                        feedback_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Deep-read the best candidates from an already paid-for retrieval pool.

        No CrustData search runs here. RankingAgent applies its cheap admission
        screen, Harvest enrichment and deep Judge only to the configured admit-N.
        """
        from backend.bridge.translate import _record_from_pool_entry, _search_intent_dataclass, shape_candidate, to_search_response
        from backend.services.role_feedback import apply_admission_tie_break, build_guidance, evidence_value
        from recruiter.agents.search.model import SearchResult

        model = self._confirmations.load(confirmation_id)
        if model is None:
            raise KeyError(confirmation_id)
        candidates = [_record_from_pool_entry(entry) for entry in entries]
        feedback_context = self._feedback_screen_context(feedback_record)
        ranking = self._pipe.ranking.rank(model, candidates, admit_all_relevant=True,
                                          feedback_context=feedback_context)
        guidance = build_guidance(feedback_record or {})
        if not guidance.empty and ranking.ranked:
            intent = _search_intent_dataclass(model)
            evidence_by_id = {}
            for row in ranking.ranked:
                candidate_id = row.record.candidate_id
                _, _, evidence = shape_candidate(model, intent, row.record, row.score, row.fit)
                evidence_by_id[candidate_id] = evidence
            ordered = apply_admission_tie_break(
                list(ranking.ranked), guidance,
                lambda row, dimension: evidence_value(dimension, evidence_by_id.get(row.record.candidate_id)),
            )
            ranking = replace(ranking, ranked=tuple(ordered), shown=tuple(ordered[:len(ranking.shown)]))
        result = SearchResult(
            candidates=tuple(candidates), pulled=len(candidates), geo_dropped=0,
            est_credits=0.0, total_available=len(candidates),
        )
        return to_search_response("platform", "", model, result, ranking, surface_all=True)

    def preview(self, confirmation_id: str):
        model = self._confirmations.load(confirmation_id)
        if model is None:
            raise KeyError(confirmation_id)
        return self._pipe.preview(model)

    def refine(self, record: Dict[str, Any], deltas: Dict[str, Any]) -> Dict[str, Any]:
        """Pool-first refine: re-check + re-rank the already-read pool against the
        recruiter's structured deltas — free, no new search. Loads the confirmed
        RoleModel so the refined cards are shaped identically. Returns the outcome
        (matched / dropped / exhausted). Mutates `record`."""
        from backend.bridge.translate import refine_pool_into_record
        confirmation_id = (record.get("confirmed_brief") or {}).get("confirmation_id")
        model = self._confirmations.load(confirmation_id) if confirmation_id else None
        if model is None:
            return {"refined": False, "matched": 0, "dropped": 0, "shown": 0, "exhausted": True}
        return refine_pool_into_record(record, model, deltas or {})

    def reveal_next(self, record: Dict[str, Any]) -> bool:
        """Bring the next already-read profile forward from the held pool (pool-
        first, no new search, no credits). Loads the confirmed RoleModel so the
        revealed card is shaped identically to the first view. Returns False if the
        confirmed brief is gone or the free pool is exhausted. Mutates `record`."""
        from backend.bridge.translate import reveal_into_record
        confirmation_id = (record.get("confirmed_brief") or {}).get("confirmation_id")
        model = self._confirmations.load(confirmation_id) if confirmation_id else None
        if model is None:
            return False
        return reveal_into_record(record, model)

    def reveal_batch(self, record: Dict[str, Any], count: int = 5) -> List[str]:
        """Reveal up to `count` already-judged profiles, without a provider request."""
        response = record.get("response") or {}
        before = {c.get("candidate_id") for c in response.get("candidates") or []}
        revealed = []
        for _ in range(max(0, count)):
            if not self.reveal_next(record):
                break
            after = (record.get("response") or {}).get("candidates") or []
            if after and after[-1].get("candidate_id"):
                revealed.append(after[-1]["candidate_id"])
        return [candidate_id for candidate_id in revealed if candidate_id not in before]
