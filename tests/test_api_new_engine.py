"""New-engine route path (RECRUITER_NEW_ENGINE): the frontend contract served by
backend.bridge.IntakeService over a fake pipeline — full flow, offline, no credits."""

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from backend.bridge.intake_service import IntakeService
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


def _reader(notes, posted_title=None):
    return Understanding(identity="eDiscovery Operations Analyst", posted_title="Operations Analyst – eDiscovery",
                         posted_title_source="jd", min_years=8,
                         requirements=(ReadRequirement("eDiscovery operations", "core", "EDRM"),))


def _service(tmp_path) -> IntakeService:
    proposer = CapabilityProposer(InMemoryCapabilityMemory(),
                                  llm_proposer=lambda *a: LearnedCapability("", "eDiscovery", ("Relativity", "Nuix"), "eDiscovery"))
    pipe = Pipeline(
        intake=IntakeAgent(reader=_reader, capability_proposer=proposer, org="example.com"),
        briefing=BriefingAgent(), calibration=CalibrationAgent(),
        search=SearchAgent(_Provider(), page_size=50),
        ranking=RankingAgent(judge=_Judge(), admit_n=25, show=5),
    )
    return IntakeService(pipe, sessions=SearchStore(storage_dir=tmp_path / "sess"),
                         confirmations=ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "conf")))


def _client(tmp_path) -> TestClient:
    app = create_app(intake_service=_service(tmp_path), search_store=SearchStore(storage_dir=tmp_path / "searches"))
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value("a@example.com"))
    return client


_BOUNDARY = {"hiring_company": "Epiq", "country": "India", "work_mode": "remote",
             "remote_scope": "anywhere", "remote_states": [], "remote_cities": []}


def test_new_engine_full_flow(tmp_path):
    c = _client(tmp_path)

    # /parse-jd -> SearchIntent shape
    si = c.post("/parse-jd", json={"jd_text": "eDiscovery ops analyst"}).json()
    assert si["role"]["title"] == "eDiscovery Operations Analyst"

    # /intake/start -> ready brief
    started = c.post("/intake/start", json={"raw_input": "eDiscovery ops", "boundary": _BOUNDARY,
                                            "posted_title": "Operations Analyst – eDiscovery"}).json()
    assert started["result"]["status"] == "ready"
    sid = started["session_id"]

    # resume + boundary edit
    assert c.get(f"/intake/{sid}").json()["session_id"] == sid
    assert c.patch(f"/intake/{sid}/boundary", json={**_BOUNDARY, "country": "India"}).status_code == 200

    # confirm -> confirmation_id
    confirmed = c.post(f"/intake/{sid}/confirmations", json={"edits": {}}).json()
    cid = confirmed["confirmation_id"]
    assert cid and confirmed["candidate_identity"] == "eDiscovery Operations Analyst"

    # /search from the confirmation -> ranked candidates
    resp = c.post("/search", json={"jd_text": "", "confirmation_id": cid, "provider": "crustdata",
                                   "autocomplete": True}).json()
    assert resp["candidate_count"] == 1 and resp["candidates"][0]["name"] == "Asha"
    assert resp["status"] == "complete"


def test_new_engine_search_requires_confirmation(tmp_path):
    c = _client(tmp_path)
    assert c.post("/search", json={"jd_text": "", "provider": "crustdata"}).status_code == 409
    assert c.post("/search", json={"jd_text": "", "confirmation_id": "bogus",
                                   "provider": "crustdata"}).status_code == 422
