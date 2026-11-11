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


def test_screener_is_high_recall_without_feedback_and_selective_with_it(monkeypatch):
    seen = {}

    def capture(system, user, model, *a, **k):
        seen["system"] = system
        return {"results": [{"i": 0, "keep": True, "score": 0.8}, {"i": 1, "keep": True, "score": 0.7}]}

    monkeypatch.setattr(llm, "complete_json", capture)
    records = (_rec("a", "AI Platform Engineer"), _rec("b", "ML Engineer"))

    # No recruiter feedback (first search) -> high-recall prompt.
    ScreenerAdapter().screen(_role(), records)
    assert "Be high-recall" in seen["system"]
    assert "recruiter validation" not in seen["system"].lower()

    # An EMPTY feedback dict is not feedback -> still high-recall.
    ScreenerAdapter().screen(_role(), records, {"shortlisted": [], "rejected": []})
    assert "Be high-recall" in seen["system"]

    # Real recruiter validation examples (campaign cycle) -> selective prompt.
    ScreenerAdapter().screen(_role(), records, {"shortlisted": [{"name": "x"}]})
    assert "Keep only likely close fits" in seen["system"]
