"""New-engine route path (RECRUITER_NEW_ENGINE): the frontend contract served by
backend.bridge.IntakeService over a fake pipeline — full flow, offline, no credits."""

import time

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


def _service(tmp_path, reader=_reader) -> IntakeService:
    proposer = CapabilityProposer(InMemoryCapabilityMemory(),
                                  llm_proposer=lambda *a: LearnedCapability("", "eDiscovery", ("Relativity", "Nuix"), "eDiscovery"))
    pipe = Pipeline(
        intake=IntakeAgent(reader=reader, capability_proposer=proposer, org="example.com"),
        briefing=BriefingAgent(), calibration=CalibrationAgent(),
        search=SearchAgent(_Provider(), page_size=50),
        ranking=RankingAgent(judge=_Judge(), admit_n=25, show=5),
    )
    return IntakeService(pipe, sessions=SearchStore(storage_dir=tmp_path / "sess"),
                         confirmations=ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "conf")))


def _client(tmp_path, reader=_reader) -> TestClient:
    app = create_app(intake_service=_service(tmp_path, reader), search_store=SearchStore(storage_dir=tmp_path / "searches"))
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value("a@example.com"))
    return client


_BOUNDARY = {"hiring_company": "Epiq", "country": "India", "work_mode": "remote",
             "remote_scope": "anywhere", "remote_states": [], "remote_cities": []}


def _poll_until_done(c, search_id, timeout=10.0):
    """POST /search now returns status='running' and the pipeline runs on a
    background thread (like the legacy Progressive Workspace), so poll GET
    /search/{id} until it leaves 'running' — exactly what the frontend does."""
    deadline = time.time() + timeout
    rec = c.get(f"/search/{search_id}").json()
    while rec.get("status") == "running" and time.time() < deadline:
        time.sleep(0.05)
        rec = c.get(f"/search/{search_id}").json()
    return rec


def _start_and_read(c, body, timeout=10.0):
    """POST /intake/start returns an 'understanding' placeholder; the ~30s read
    runs on a background thread. Poll GET /intake/{id} until the brief is ready —
    exactly what the frontend does — and return (session_id, latest response)."""
    started = c.post("/intake/start", json=body).json()
    sid = started["session_id"]
    deadline = time.time() + timeout
    data = started
    while data["result"]["status"] == "understanding" and time.time() < deadline:
        time.sleep(0.05)
        data = c.get(f"/intake/{sid}").json()
    return sid, data


def test_new_engine_full_flow(tmp_path):
    c = _client(tmp_path)

    # /parse-jd -> SearchIntent shape
    si = c.post("/parse-jd", json={"jd_text": "eDiscovery ops analyst"}).json()
    assert si["role"]["title"] == "eDiscovery Operations Analyst"

    # /intake/start -> 'understanding' placeholder, then background read -> ready brief (polled)
    sid, started = _start_and_read(c, {"raw_input": "eDiscovery ops", "boundary": _BOUNDARY,
                                       "posted_title": "Operations Analyst – eDiscovery"})
    assert started["result"]["status"] == "ready"

    # resume + boundary edit
    assert c.get(f"/intake/{sid}").json()["session_id"] == sid
    assert c.patch(f"/intake/{sid}/boundary", json={**_BOUNDARY, "country": "India"}).status_code == 200

    # confirm -> confirmation_id
    confirmed = c.post(f"/intake/{sid}/confirmations", json={"edits": {}}).json()
    cid = confirmed["confirmation_id"]
    assert cid and confirmed["candidate_identity"] == "eDiscovery Operations Analyst"

    # /search from the confirmation -> returns immediately as 'running', then the
    # background thread fills in the ranked candidates (polled like the frontend).
    posted = c.post("/search", json={"jd_text": "", "confirmation_id": cid, "provider": "crustdata",
                                     "autocomplete": True}).json()
    assert posted["status"] == "running"
    resp = _poll_until_done(c, posted["search_id"])
    assert resp["status"] == "complete"
    assert resp["candidate_count"] == 1 and resp["candidates"][0]["name"] == "Asha"


def test_confirm_singular_returns_search_intent_preview(tmp_path):
    # The frontend auto-fires POST /intake/{id}/confirm (singular) on brief load
    # to preview the search intent — this must NOT 503 on the new engine.
    c = _client(tmp_path)
    sid, _ = _start_and_read(c, {"raw_input": "eDiscovery ops", "boundary": _BOUNDARY})
    r = c.post(f"/intake/{sid}/confirm")
    assert r.status_code == 200
    assert r.json()["role"]["title"] == "eDiscovery Operations Analyst"


def test_company_include_exclude_tags_flow_through(tmp_path):
    c = _client(tmp_path)
    boundary = {**_BOUNDARY, "include_companies": ["KLDiscovery", "Consilio"],
                "exclude_companies": ["RivalCorp"]}
    sid, _ = _start_and_read(c, {"raw_input": "eDiscovery ops", "boundary": boundary})
    si = c.post(f"/intake/{sid}/confirmations", json={"edits": {}}).json()["search_intent"]
    assert si["company_preferences"]["preferred_companies_ever"] == ["KLDiscovery", "Consilio"]  # include = OR
    # exclude = recruiter's list + the always-excluded hiring company
    assert set(si["company_preferences"]["exclude_current_companies"]) == {"Epiq", "RivalCorp"}


def test_boundary_min_years_over_http_prevents_clarification(tmp_path):
    # Full HTTP path: JD omits years, recruiter supplies min_years in the boundary.
    def no_years(notes, posted_title=None):
        return Understanding(identity="Director", min_years=None, requirements=(ReadRequirement("x", "core"),))
    c = _client(tmp_path, reader=no_years)
    body = {"raw_input": "Senior Director JD", "boundary": {**_BOUNDARY, "min_years": 10, "max_years": 15}}
    _, res = _start_and_read(c, body)
    assert res["result"]["status"] == "ready"
    ec = res["result"]["role_understanding"]["explicit_constraints"]
    assert ec["experience_minimum_years"] == 10 and ec["experience_maximum_years"] == 15


def test_new_engine_search_requires_confirmation(tmp_path):
    c = _client(tmp_path)
    # No confirmation at all is a synchronous 409 — nothing to run.
    assert c.post("/search", json={"jd_text": "", "provider": "crustdata"}).status_code == 409
    # A confirmation id that does not resolve is rejected synchronously too, before any background
    # work is started (the campaign validates its confirmed brief up front rather than starting a doomed cycle).
    r = c.post("/search", json={"jd_text": "", "confirmation_id": "bogus", "provider": "crustdata"})
    assert r.status_code == 409
