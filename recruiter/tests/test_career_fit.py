"""Tier-2 career-fit assessor — offline (the LLM call is monkeypatched)."""

import recruiter.llm as llm
from recruiter.agents.ranking.career_fit import CareerFitAssessor
from recruiter.candidates import CandidateRecord
from recruiter.role_model import ARCHITECT, JD, Location, Provenance, Requirement, RoleModel, Seniority


def _role():
    return RoleModel(
        identity="AI Platform Engineer",
        seniority=Seniority(8, None, Provenance(JD)),
        role_level=ARCHITECT,
        location=Location(countries=("Canada",)),
        requirements=(Requirement("Agentic AI", "core", Provenance(JD)),),
    )


def _rec():
    return CandidateRecord(candidate_id="c1", name="Dev", title="Senior AI Platform Engineer",
                           raw={"basic_profile": {"headline": "AI platform, RAG, agents"}})


def test_assessor_parses_score_and_rationale(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"score": 0.82, "rationale": "Decade of AI platform work."})
    out = CareerFitAssessor().assess(_role(), _rec())
    assert out["score"] == 0.82 and "AI platform" in out["rationale"]


def test_assessor_clamps_and_defaults(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"score": 1.7})  # out of range, no rationale
    out = CareerFitAssessor().assess(_role(), _rec())
    assert out["score"] == 1.0 and out["rationale"] == ""
