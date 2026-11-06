"""Tier-1 admission screener — offline (the LLM call is monkeypatched)."""

import recruiter.llm as llm
from recruiter.agents.ranking.screener_adapter import ScreenerAdapter
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


def _rec(cid, title, headline=""):
    return CandidateRecord(candidate_id=cid, name=cid, title=title,
                           raw={"basic_profile": {"headline": headline}})


def test_screener_parses_keep_and_score_and_keeps_unanswered(monkeypatch):
    records = (_rec("a", "AI Platform Engineer", "Agentic AI"), _rec("b", "Data Analyst"), _rec("c", "ML Engineer"))
    # The model answers a (keep) and b (drop) but forgets c — unanswered must default to keep.
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"results": [
        {"i": 0, "keep": True, "score": 0.9},
        {"i": 1, "keep": False, "score": 0.1},
    ]})
    out = ScreenerAdapter().screen(_role(), records)
    assert [r.keep for r in out] == [True, False, True]
    assert out[0].score == 0.9 and out[2].score == 0.5


def test_screener_fails_open_on_an_llm_error(monkeypatch):
    records = (_rec("a", "AI Platform Engineer"), _rec("b", "ML Engineer"))

    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(llm, "complete_json", boom)
    out = ScreenerAdapter().screen(_role(), records)
    assert all(r.keep for r in out)  # a broken gate never drops anyone


def test_screener_on_empty_batch_is_empty():
    assert ScreenerAdapter().screen(_role(), ()) == ()
