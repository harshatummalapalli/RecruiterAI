"""IntakeService feature A — dual-source read_into + reconciliation in get(), offline."""

import pytest

pytest.importorskip("backend.services.search_store")

from backend.bridge.intake_service import IntakeService
from backend.bridge.session_store import ConfirmationStore
from backend.services.search_store import SearchStore
from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake import IntakeAgent, Understanding
from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import ReadRequirement
from recruiter.agents.intake.reconcile import token_matcher
from recruiter.agents.ranking import RankingAgent
from recruiter.agents.search import SearchAgent
from recruiter.pipeline import Pipeline

_BOUNDARY = {"hiring_company": "Northwind", "country": "India", "work_mode": "onsite", "min_years": 3}


class _Provider:
    def count(self, query):
        return 1

    def search(self, query, page_size):
        return []


class _Judge:
    def judge(self, role, record):
        return ()


def _reader(notes, posted_title=None):
    if notes.strip().startswith("HM"):
        return Understanding(identity="Software Engineer", min_years=5,
                             requirements=(ReadRequirement("Python", "core"),
                                           ReadRequirement("Payments infrastructure", "supporting")))
    return Understanding(identity="Software Engineer", posted_title="Software Engineer",
                         posted_title_source="jd", min_years=3,
                         requirements=(ReadRequirement("Python", "core"),
                                       ReadRequirement("Agile methodology", "core")))


def _service(reader, tmp_path):
    pipe = Pipeline(
        intake=IntakeAgent(reader=reader, capability_proposer=CapabilityProposer(InMemoryCapabilityMemory()),
                           org="t", matcher_factory=lambda jd, hm: token_matcher),
        briefing=BriefingAgent(), calibration=CalibrationAgent(),
        search=SearchAgent(_Provider(), page_size=50),
        ranking=RankingAgent(judge=_Judge(), admit_n=25, show=5),
    )
    return IntakeService(pipe, sessions=SearchStore(storage_dir=tmp_path / "s"),
                         confirmations=ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "c")))


def test_dual_source_reconciliation_surfaces_in_get(tmp_path):
    svc = _service(_reader, tmp_path)
    sid = svc.begin("JD text", _BOUNDARY, posted_title="Software Engineer", hm_notes="HM call: 5+ years")["session_id"]
    svc.read_into(sid)

    got = svc.get(sid)
    recon = got["reconciliation"]
    assert recon is not None
    tiers = {r["text"]: (r["tier"], r["source"]) for r in recon["requirements"]}
    assert tiers["Payments infrastructure"] == ("core", "hm")      # HM-only -> promoted
    assert tiers["Agile methodology"] == ("supporting", "jd")      # JD-only -> demoted
    assert tiers["Python"][1] == "both"
    # years sanity-catch: recruiter filter 3 vs HM prose 5
    assert recon["experience"] == {"boundary_years": 3, "hm_mentioned_years": 5}
    # the merged read still drives a normal, ready brief
    assert got["result"]["status"] == "ready"


def test_single_source_has_no_reconciliation(tmp_path):
    svc = _service(_reader, tmp_path)
    sid = svc.begin("JD text", _BOUNDARY, posted_title="Software Engineer")["session_id"]   # no hm_notes
    svc.read_into(sid)
    assert svc.get(sid)["reconciliation"] is None


def test_experience_flag_silent_when_years_agree(tmp_path):
    svc = _service(_reader, tmp_path)
    # boundary filter 5 matches the HM's 5 -> no flag
    sid = svc.begin("JD text", {**_BOUNDARY, "min_years": 5}, hm_notes="HM call: 5+ years")["session_id"]
    svc.read_into(sid)
    assert svc.get(sid)["reconciliation"]["experience"] is None


def test_reconciliation_survives_a_boundary_edit(tmp_path):
    svc = _service(_reader, tmp_path)
    sid = svc.begin("JD text", _BOUNDARY, hm_notes="HM call: 5+ years")["session_id"]
    svc.read_into(sid)
    svc.update_boundary(sid, {**_BOUNDARY, "country": "USA"})       # a later re-save
    assert svc.get(sid)["reconciliation"] is not None              # sticky, not wiped
