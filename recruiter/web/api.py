"""FastAPI over recruiter.pipeline — the recruiter's staged flow:

  POST /api/intake    notes + boundary (+ optional years) -> intent review +
                      adaptive questions, OR a clarification (missing years)
  POST /api/execute   session + answers -> authorise -> search + rank (SPENDS
                      CrustData credits) -> ranked candidates with evidence
  GET  /api/admin/query?session=…   the raw CrustData query (admin-only view)
  GET  /                            the minimal recruiter UI

Sessions are in-process (one recruiter, local): fine for the quick-win UI;
Supabase replaces this at the infra migration. The pipeline is injectable so
the whole surface tests offline with no credits.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

_STATIC = Path(__file__).resolve().parent / "static"


class IntakeBody(BaseModel):
    notes: str
    boundary: Dict[str, Any] = Field(default_factory=dict)
    answers: Dict[str, Any] = Field(default_factory=dict)   # e.g. {"min_years": 8}


class ExecuteBody(BaseModel):
    session: str
    answers: Dict[str, Any] = Field(default_factory=dict)


# Short UI keys -> the CrustData filter field they autocomplete (raw paths stay
# server-side, so the UI can't query arbitrary columns).
_AC_FIELDS = {
    "country": "basic_profile.location.country",
    "state": "basic_profile.location.state",
    "city": "basic_profile.location.city",
    "industry": "experience.employment_details.current.company_industries",
    # Latent (Tier 3) — education is a capability, off by default; autocomplete is
    # ready so a school/branch picker can be added if a recruiter asks for it.
    "school": "education.schools.school",
    "field_of_study": "education.schools.field_of_study",
}


def _question(q) -> Dict[str, Any]:
    return {"id": q.id, "kind": q.kind, "prompt": q.prompt, "routing": q.routing,
            "required": q.required, "options": list(q.options)}


def create_app(pipeline=None, org: str = "default") -> FastAPI:
    app = FastAPI(title="RecruiterAI (rearch)")
    state: Dict[str, Any] = {"pipeline": pipeline}
    sessions: Dict[str, Dict[str, Any]] = {}

    def get_pipeline():
        if state["pipeline"] is None:
            from recruiter.live import build_live_pipeline
            state["pipeline"] = build_live_pipeline(org=org)
        return state["pipeline"]

    @app.get("/")
    def index():
        return FileResponse(_STATIC / "index.html")

    @app.post("/api/intake")
    def intake(body: IntakeBody):
        pipe = get_pipeline()
        try:
            outcome = pipe.read_intent(body.notes, body.boundary, body.answers or None)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Intake failed: {exc}")
        if not outcome.ready:
            return {"ready": False, "clarifications": [_question(q) for q in outcome.clarifications]}

        _, review = pipe.prepare_review(outcome)
        session_id = str(uuid.uuid4())
        sessions[session_id] = {"model": outcome.model, "questions": review.questions}
        return {
            "ready": True,
            "session": session_id,
            "review": {
                "summary": [{"label": ln.label, "value": ln.value} for ln in review.summary],
                "limits": list(review.limits),
                "questions": [_question(q) for q in review.questions],
            },
        }

    @app.get("/api/autocomplete")
    def autocomplete(field: str, q: str = "", limit: int = 8):
        """Canonical-value typeahead for the geo/industry dropdowns (free)."""
        col = _AC_FIELDS.get(field)
        if not col:
            raise HTTPException(status_code=400, detail=f"unknown autocomplete field: {field}")
        if not q.strip():
            return {"values": []}
        try:
            values = get_pipeline().search.autocomplete(col, q.strip(), min(max(int(limit), 1), 15))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Autocomplete failed: {exc}")
        return {"values": values}

    @app.get("/api/preview")
    def preview(session: str):
        """Free confidence signal: how many profiles match this intent (~0.03 cr),
        before any paid search. Shown on the review so the recruiter can tighten or
        widen the filters until the pool looks right."""
        sess = sessions.get(session)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found — re-run Analyze.")
        try:
            matched, preview_credits = get_pipeline().preview(sess["model"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Preview failed: {exc}")
        return {"matched": matched, "preview_credits": preview_credits}

    @app.post("/api/execute")
    def execute(body: ExecuteBody):
        sess = sessions.get(body.session)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found — re-run Analyze.")
        pipe = get_pipeline()
        try:
            auth, search, ranking = pipe.execute(sess["model"], body.answers or {}, sess["questions"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Search failed: {exc}")
        if not auth.authorized:
            return {"authorized": False, "reason": auth.blocked_reason}
        sessions[body.session]["model"] = auth.model  # keep the answered model for the admin view
        return {
            "authorized": True,
            "search": {"pulled": search.pulled, "geo_dropped": search.geo_dropped,
                       "excluded_dropped": search.excluded_dropped, "est_credits": search.est_credits},
            "stats": {"admitted": ranking.admitted, "judged": ranking.judged,
                      "judge_failures": ranking.judge_failures, "experience_excluded": ranking.experience_excluded},
            "candidates": [
                {"name": rc.record.name, "title": rc.record.title, "company": rc.record.company,
                 "location": rc.record.location, "profile_url": rc.record.profile_url,
                 "score": rc.score, "fit": rc.fit}
                for rc in ranking.shown
            ],
        }

    @app.get("/api/admin/query")
    def admin_query(session: str):
        sess = sessions.get(session)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        plan = get_pipeline().briefing.build(sess["model"])
        return get_pipeline().calibration.admin_query(plan)

    return app


app = create_app()
