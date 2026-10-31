"""Web API over the pipeline — offline (fake I/O, no credits) via TestClient."""

import pytest
from fastapi.testclient import TestClient

from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake import IntakeAgent
from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory, LearnedCapability
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.agents.ranking import RankingAgent
from recruiter.agents.search import SearchAgent
from recruiter.candidates import CandidateRecord
from recruiter.pipeline import Pipeline
from recruiter.web.api import create_app


def _understanding(notes, posted_title=None):
    return Understanding(identity="AI Architect", posted_title="AI Architect", min_years=12,
                         work_mode_in_notes="remote",
                         requirements=(ReadRequirement("Agentic Systems", "core", when="current"),
                                       ReadRequirement("Python", "core", when="current")))


class _Provider:
    def count(self, query):
        return 1234

    def search(self, query, page_size):
        return [CandidateRecord("real", name="Real", title="AI Architect", location="Pune, India",
                                raw={"basic_profile": {"headline": "Agentic Systems and Python in production"}},
                                matched_queries=("natural_language",)),
                CandidateRecord("weak", name="Weak", title="AI Architect", location="Pune, India",
                                raw={"basic_profile": {"headline": "generalist"}})]


class _Judge:
    def judge(self, role, record):
        hl = ((record.raw.get("basic_profile") or {}).get("headline") or "").lower()
        return tuple({"tier": r.tier, "signal_text": r.text, "quote": r.text if r.text.split()[0].lower() in hl else "",
                      "verdict": "met" if r.text.split()[0].lower() in hl else "not_evidenced"} for r in role.requirements)


def _client(reader=_understanding):
    proposer = CapabilityProposer(InMemoryCapabilityMemory(),
                                  llm_proposer=lambda *a: LearnedCapability("", "Agentic AI", ("agentic", "LLM"), "AI"))
    pipe = Pipeline(
        intake=IntakeAgent(reader=reader, capability_proposer=proposer, org="t"),
        briefing=BriefingAgent(), calibration=CalibrationAgent(),
        search=SearchAgent(_Provider(), page_size=50),
        ranking=RankingAgent(judge=_Judge(), admit_n=25, show=5),
    )
    return TestClient(create_app(pipeline=pipe))


BODY = {"notes": "AI Architect, Agentic + Python, 12y, India, Epiq",
        "boundary": {"hiring_company": "Epiq", "country": "India", "work_mode": "remote",
                     "preferred_cities": ["Hyderabad", "Bengaluru", "Pune"]}}


def test_intake_returns_review_and_questions():
    r = _client().post("/api/intake", json=BODY).json()
    assert r["ready"] is True and r["session"]
    labels = {ln["label"] for ln in r["review"]["summary"]}
    assert "Role" in labels and "Location" in labels
    assert any(q["id"] == "capability" for q in r["review"]["questions"])


def test_execute_returns_ranked_candidates():
    c = _client()
    session = c.post("/api/intake", json=BODY).json()["session"]
    res = c.post("/api/execute", json={"session": session, "answers": {"dealbreakers": ["Agentic Systems"]}}).json()
    assert res["authorized"] is True
    assert res["candidates"][0]["name"] == "Real"
    assert "Evidence:" in res["candidates"][0]["fit"]
    assert res["search"]["est_credits"] > 0


def test_preview_returns_pool_count():
    c = _client()
    session = c.post("/api/intake", json=BODY).json()["session"]
    r = c.get("/api/preview", params={"session": session}).json()
    assert r["matched"] == 1234 and r["preview_credits"] == 0.03


def test_preview_graceful_without_count_support():
    class _NoCount:
        def search(self, query, page_size):
            return []
    agent = SearchAgent(_NoCount(), page_size=50)
    from recruiter.agents.briefing.model import ProviderQuery
    assert agent.preview_count(ProviderQuery(natural_language="x")) is None


def test_confirm_no_blocks_execution():
    c = _client()
    session = c.post("/api/intake", json=BODY).json()["session"]
    res = c.post("/api/execute", json={"session": session, "answers": {"confirm_level": "no"}}).json()
    assert res["authorized"] is False and "correct the role" in res["reason"]


def test_missing_years_returns_clarification():
    def no_years(notes, posted_title=None):
        return Understanding(identity="AI Architect", min_years=None, requirements=(ReadRequirement("x", "core"),))
    r = _client(reader=no_years).post("/api/intake", json=BODY).json()
    assert r["ready"] is False and r["clarifications"][0]["kind"] == "min_years"


def test_unknown_session_is_404():
    assert _client().post("/api/execute", json={"session": "nope", "answers": {}}).status_code == 404
