"""IntakeService over the new pipeline — full intake->confirm->search flow, offline."""

import pytest

pytest.importorskip("backend.services.search_store")

from backend.bridge.intake_service import ConfirmationNotReady, IntakeService
from backend.bridge.session_store import ConfirmationStore
from backend.services.search_store import SearchStore
from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake import IntakeAgent, Understanding
from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory, LearnedCapability
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import ReadRequirement
from recruiter.agents.ranking import RankingAgent
from recruiter.agents.search import SearchAgent
from recruiter.candidates import CandidateRecord
from recruiter.pipeline import Pipeline


class _Provider:
    def count(self, query):
        return 4321

    def search(self, query, page_size):
        return [CandidateRecord("real", name="Asha", title="eDiscovery Analyst", company="KLDiscovery",
                                location="Pune, India",
                                raw={"basic_profile": {"headline": "Relativity Nuix eDiscovery"}},
                                matched_queries=("natural_language",))]


class _Judge:
    def judge(self, role, record):
        return tuple({"tier": r.tier, "signal_text": r.text, "quote": r.text, "verdict": "met"}
                     for r in role.requirements)


def _pipeline(reader):
    proposer = CapabilityProposer(InMemoryCapabilityMemory(),
                                  llm_proposer=lambda *a: LearnedCapability("", "eDiscovery", ("Relativity", "Nuix"), "eDiscovery"))
    return Pipeline(
        intake=IntakeAgent(reader=reader, capability_proposer=proposer, org="dayzero.partners"),
        briefing=BriefingAgent(), calibration=CalibrationAgent(),
        search=SearchAgent(_Provider(), page_size=50),
        ranking=RankingAgent(judge=_Judge(), admit_n=25, show=5),
    )


def _service(reader, tmp_path):
    return IntakeService(_pipeline(reader),
                         sessions=SearchStore(storage_dir=tmp_path / "sessions"),
                         confirmations=ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "conf")))


def _ready_reader(notes, posted_title=None):
    return Understanding(identity="eDiscovery Operations Analyst", posted_title="Operations Analyst – eDiscovery",
                         posted_title_source="jd", min_years=8,
                         requirements=(ReadRequirement("eDiscovery operations", "core", "EDRM"),))


_BOUNDARY = {"hiring_company": "Epiq", "country": "India", "work_mode": "onsite"}


def test_start_ready_then_confirm_then_search(tmp_path):
    svc = _service(_ready_reader, tmp_path)
    started = svc.start("JD text", _BOUNDARY, posted_title="Operations Analyst – eDiscovery")
    assert started["result"]["status"] == "ready"
    sid = started["session_id"]
    assert started["result"]["role_understanding"]["primary_candidate_identity"]["value"] == "eDiscovery Operations Analyst"

    confirmed = svc.confirm(sid, edits={})
    cid = confirmed["confirmation_id"]
    assert cid and confirmed["candidate_identity"] == "eDiscovery Operations Analyst"

    resp = svc.run_search(cid, "search-1")
    assert resp["candidate_count"] == 1 and resp["candidates"][0]["name"] == "Asha"
    assert resp["diagnostics"]["pulled"] == 1


def test_answering_a_refinement_clears_it(tmp_path):
    svc = _service(_ready_reader, tmp_path)
    started = svc.start("JD", _BOUNDARY, posted_title="Operations Analyst – eDiscovery")
    sid = started["session_id"]
    ids = {i["id"] for i in started["result"]["decision"]["issues"]}
    assert "capability" in ids                       # refinement shown
    answered = svc.answer(sid, "capability", "keep", "keep")
    cleared = {i["id"] for i in answered["result"]["decision"]["issues"]}
    assert "capability" not in cleared               # answered -> gone (card clears)


def test_missing_years_clarifies_then_resolves(tmp_path):
    def no_years(notes, posted_title=None):
        return Understanding(identity="Analyst", min_years=None,
                             requirements=(ReadRequirement("ops", "core"),))
    svc = _service(no_years, tmp_path)
    started = svc.start("JD", _BOUNDARY)
    assert started["result"]["status"] == "needs_clarification"
    sid = started["session_id"]
    assert started["result"]["decision"]["issues"][0]["id"] == "min_years"

    answered = svc.answer(sid, "min_years", "6", "6 years")
    assert answered["result"]["status"] == "ready"
    assert answered["result"]["role_understanding"]["explicit_constraints"]["experience_minimum_years"] == 6


def test_confirm_blocks_when_not_ready(tmp_path):
    def no_years(notes, posted_title=None):
        return Understanding(identity="Analyst", min_years=None, requirements=(ReadRequirement("ops", "core"),))
    svc = _service(no_years, tmp_path)
    sid = svc.start("JD", _BOUNDARY)["session_id"]
    with pytest.raises(ConfirmationNotReady):
        svc.confirm(sid, edits={})


def test_update_boundary_is_deterministic_no_reread(tmp_path):
    calls = {"n": 0}
    def counting_reader(notes, posted_title=None):
        calls["n"] += 1
        return _ready_reader(notes, posted_title)
    svc = _service(counting_reader, tmp_path)
    sid = svc.start("JD", _BOUNDARY)["session_id"]
    assert calls["n"] == 1
    out = svc.update_boundary(sid, {**_BOUNDARY, "country": "USA"})
    assert out["boundary"]["country"] == "USA" and calls["n"] == 1  # assemble only, no re-read


def test_get_unknown_session_returns_none(tmp_path):
    assert _service(_ready_reader, tmp_path).get("nope") is None
