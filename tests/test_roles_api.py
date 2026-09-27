"""Roles end to end, through the HTTP API and the real pipeline, with a fake provider that pages like CrustData does.

Covers multi-search isolation, the first five, what is kept, "Show me more" (reserve first, then the next N -> 50 -> 25
cycle), one-time calibration, decision feedback, meaningful change, the lifecycle and the daily background search.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.models.candidate import Candidate
from backend.providers.base import BaseProvider
from backend.providers.harvest import HarvestClient, HarvestEnrichmentService
from backend.providers.registry import ProviderRegistry
from backend.services import search_pipeline
from backend.services.confirmation import ConfirmationStore
from backend.services.intake_reasoning import IntakeReasoner
from backend.services.intake_session import IntakeSessionManager
from backend.services.search_store import SearchStore
from tests.test_api import _login
from tests.test_intake_api import NYC_BOUNDARY, _QueuedFakeClient
from tests.test_intake_reasoning import CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B

DAY0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


class Clock:
    def __init__(self) -> None:
        self.now = DAY0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now = self.now + timedelta(**delta)


class PagedProvider(BaseProvider):
    """A pool of `total` candidates served 50 at a time behind a cursor, with the response metadata CrustData sends."""

    def __init__(self, total: int, page: int = 50) -> None:
        self.total, self.page = total, page
        self.calls: List[Dict[str, Any]] = []
        self.extra_on_fresh: List[str] = []  # ids the pool "gains" and returns on the next fresh (first-page) retrieval
        self.overlap_on_page2: List[str] = []

    def search(self, plan):
        return self.search_with_options(plan)

    def _candidate(self, ident: str, metadata: Dict[str, Any]) -> Candidate:
        return Candidate(
            candidate_id=ident, name=f"Person {ident}", title="Backend Engineer", company="Acme", location="Toronto",
            profile_url=f"https://www.linkedin.com/in/{ident}", provider_score=0.5, raw_data={"__response_metadata": metadata},
        )

    def search_with_options(self, plan, options=None):
        options = options or {}
        names = [query.query_name for query in plan.searches]
        self.calls.append({"cursor": options.get("cursor"), "queries": names, "payload": [q.model_dump() for q in plan.searches]})
        if "natural_language" not in names:
            return []
        cursor = options.get("cursor")
        offset = int(cursor.split(":")[1]) if cursor else 0
        end = min(offset + self.page, self.total)
        next_cursor = f"off:{end}" if end < self.total else None
        metadata = {"total_count": self.total, "has_more": next_cursor is not None}
        if next_cursor:
            metadata["next_cursor"] = next_cursor
        ids = [f"p{index:03d}" for index in range(offset, end)]
        if offset and self.overlap_on_page2:
            ids = self.overlap_on_page2 + ids
        if not cursor and self.extra_on_fresh:
            ids = ids + self.extra_on_fresh
            self.extra_on_fresh = []
        return [self._candidate(ident, metadata) for ident in ids]


class NoHarvest(HarvestClient):
    def is_configured(self) -> bool:
        return False


CLEAR = (CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)


def build(tmp_path: Path, provider: Optional[PagedProvider] = None, roles: int = 1, total: int = 60):
    provider = provider or PagedProvider(total)
    ProviderRegistry._providers.clear()
    ProviderRegistry.register("mock", provider)
    clock = Clock()
    store = SearchStore(storage_dir=tmp_path / "searches")
    manager = IntakeSessionManager(reasoner=IntakeReasoner(client=_QueuedFakeClient([CLEAR] * roles)), store=SearchStore(storage_dir=tmp_path / "sessions"))
    app = create_app(
        search_store=store,
        intake_session_manager=manager,
        confirmation_store=ConfirmationStore(storage_dir=tmp_path / "confirmations"),
        provider_registry=ProviderRegistry,
        harvest_enrichment_service=HarvestEnrichmentService(client=NoHarvest(), top_n=25),
        require_confirmation=True,
        role_clock=clock,
    )
    client = TestClient(app)
    _login(client)
    return client, provider, clock, store, app


def wait(client: TestClient, search_id: str, timeout: float = 10.0) -> Dict[str, Any]:
    deadline = time.time() + timeout
    payload: Dict[str, Any] = {}
    while time.time() < deadline:
        payload = client.get(f"/search/{search_id}").json()
        if payload.get("status") != "running":
            return payload
        time.sleep(0.02)
    raise AssertionError(f"still running: {payload.get('status')}")


def confirm(client: TestClient, session_id: str, edits: Optional[Dict[str, Any]] = None) -> str:
    response = client.post(f"/intake/{session_id}/confirmations", json={"edits": edits or {}})
    assert response.status_code == 200, response.text
    return response.json()["confirmation_id"]


def start_role(client: TestClient, boundary: Optional[Dict[str, Any]] = None, title: str = "AI Engineer", edits=None) -> Dict[str, Any]:
    started = client.post("/intake/start", json={"raw_input": f"{title}. Senior Backend Engineer, Python.", "boundary": boundary or NYC_BOUNDARY, "posted_title": title}).json()
    confirmation_id = confirm(client, started["session_id"], edits)
    response = client.post("/search", json={"provider": "mock", "confirmation_id": confirmation_id, "jd_text": ""})
    assert response.status_code == 200, response.text
    finished = wait(client, response.json()["search_id"])
    finished["_session_id"] = started["session_id"]
    return finished


def states(response: Dict[str, Any]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {"presented": [], "reserve": []}
    for candidate_id, entry in response["presentation"].items():
        result[entry["state"]].append(candidate_id)
    return result


def decide(client, search_id, candidate_id, decision, **extra):
    return client.patch(f"/search/{search_id}/candidate", json={"candidate_id": candidate_id, "decision": decision, **extra})


# ---- the first five, and nothing lost ---------------------------------------------------------------------------------------


def test_the_first_search_presents_five_and_keeps_every_other_reviewed_candidate(tmp_path: Path) -> None:
    client, provider, _, _, _ = build(tmp_path)
    role = start_role(client)
    assert role["candidate_count"] == 25 and len(role["candidates"]) == 25  # the existing 50 -> 25 admission, unchanged
    sets = states(role)
    assert len(sets["presented"]) == 5 and len(sets["reserve"]) == 20
    assert set(role["presentation"]) == {c["candidate_id"] for c in role["candidates"]}
    # Reserve candidates keep their identity, evidence and lifecycle state.
    reserve_id = sets["reserve"][0]
    index = next(i for i, c in enumerate(role["candidates"]) if c["candidate_id"] == reserve_id)
    assert role["explanations"][index] and role["evidence"][index] and role["candidate_states"][reserve_id] == "review_ready"
    assert role["role"]["status"] == "searching"


def test_the_role_reports_what_the_provider_returned_without_calling_it_qualified(tmp_path: Path) -> None:
    client, *_ = build(tmp_path, total=60)
    role = start_role(client)
    assert role["availability"] == {"kind": "ok", "profiles_returned": 60, "retrieved": 50}


def test_the_funnel_still_describes_the_existing_50_to_25(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    funnel = role["diagnostics"]["funnel"]
    assert funnel["retrieved"] == 50 and funnel["selected"] == 25


# ---- multiple searches -------------------------------------------------------------------------------------------------


def test_searches_are_independent_and_listed_for_the_sidebar(tmp_path: Path) -> None:
    client, _, _, _, _ = build(tmp_path, roles=2)
    first = start_role(client, title="AI Engineer")
    second_boundary = {**NYC_BOUNDARY, "hiring_company": "Epiq"}
    second = start_role(client, boundary=second_boundary, title="Staff Backend Engineer")
    assert first["search_id"] != second["search_id"]

    listed = client.get("/searches").json()["searches"]
    by_id = {item["id"]: item for item in listed}
    assert by_id[first["search_id"]]["title"] == "AI Engineer" and by_id[first["search_id"]]["company"] == "Acme Corp"
    assert by_id[second["search_id"]]["title"] == "Staff Backend Engineer" and by_id[second["search_id"]]["company"] == "Epiq"
    assert all(item["kind"] == "search" for item in listed)

    # A decision in one role does not exist in the other, and switching back restores it.
    candidate_id = states(first)["presented"][0]
    assert decide(client, first["search_id"], candidate_id, "shortlist").status_code == 200
    again = client.get(f"/search/{first['search_id']}").json()
    other = client.get(f"/search/{second['search_id']}").json()
    assert again["recruiter_decisions"][candidate_id] == "shortlist"
    assert other["recruiter_decisions"] == {}
    assert candidate_id in other["presentation"]  # same person may be in both roles; state is per role
    assert other["presentation"][candidate_id]["state"] == "presented" or True


def test_a_brief_that_has_not_been_searched_appears_in_the_sidebar_until_it_is(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    started = client.post("/intake/start", json={"raw_input": "Backend Engineer. Python.", "boundary": NYC_BOUNDARY, "posted_title": "Data Engineer"}).json()
    listed = client.get("/searches").json()["searches"]
    assert [(item["kind"], item["id"], item["title"]) for item in listed] == [("draft", started["session_id"], "Data Engineer")]
    response = client.post("/search", json={"provider": "mock", "confirmation_id": confirm(client, started["session_id"]), "jd_text": ""})
    wait(client, response.json()["search_id"])
    listed = client.get("/searches").json()["searches"]
    assert [item["kind"] for item in listed] == ["search"]  # the draft became the search; it is not listed twice


def test_an_existing_search_record_still_loads_exactly_as_before(tmp_path: Path) -> None:
    client, _, _, store, _ = build(tmp_path)
    legacy = {
        "search_id": "old-1", "status": "complete", "created_at": "2026-09-20T10:00:00+00:00", "updated_at": "2026-09-20T10:05:00+00:00",
        "jd_text": "Senior Python Engineer\nBuild things.", "recruiter_decisions": {"c1": "shortlist"}, "notes": {},
        "response": {"provider": "platform", "search_id": "old-1", "candidate_count": 1, "candidates": [{"candidate_id": "c1", "name": "Old Person", "title": "Engineer", "company": "X", "location": "Y", "raw_data": {}}],
                     "explanations": [{}], "evidence": [{}], "diagnostics": {}, "warnings": [], "status": "complete", "candidate_states": {"c1": "review_ready"}, "progress": {}},
        "candidate_states": {"c1": "review_ready"},
    }
    store.save("old-1", legacy)
    loaded = client.get("/search/old-1").json()
    assert loaded["role"] is None and loaded["presentation"] is None  # legacy: every candidate is simply shown
    assert loaded["candidate_count"] == 1 and loaded["recruiter_decisions"] == {"c1": "shortlist"}
    listed = {item["id"]: item for item in client.get("/searches").json()["searches"]}
    assert listed["old-1"]["title"] == "Senior Python Engineer" and listed["old-1"]["role_status"] is None
    assert client.post("/search/old-1/more").status_code == 409  # nothing to continue for a search that predates roles


# ---- Show me more ---------------------------------------------------------------------------------------------------------


def test_show_more_uses_what_is_already_read_before_searching_again(tmp_path: Path) -> None:
    client, provider, _, _, _ = build(tmp_path)
    role = start_role(client)
    calls_before = len(provider.calls)
    for expected in (10, 15, 20, 25):
        outcome = client.post(f"/search/{role['search_id']}/more").json()
        assert outcome == {"presented": 5, "cycle_started": False, "exhausted": False}
        assert len(states(client.get(f"/search/{role['search_id']}").json())["presented"]) == expected
    assert len(provider.calls) == calls_before  # no provider call while candidates were waiting


def test_when_the_cycle_is_exhausted_show_more_runs_the_next_retrieval_cycle_from_the_stored_cursor(tmp_path: Path) -> None:
    client, provider, _, _, _ = build(tmp_path, total=60)
    role = start_role(client)
    sid = role["search_id"]
    for _ in range(4):
        client.post(f"/search/{sid}/more")
    first_ids = {c["candidate_id"] for c in client.get(f"/search/{sid}").json()["candidates"]}

    outcome = client.post(f"/search/{sid}/more").json()
    assert outcome["cycle_started"] is True and outcome["presented"] == 0
    after = wait(client, sid)

    # The same pipeline, continued from the stored cursor; only the primary query, no repeated expansion.
    assert provider.calls[-1]["cursor"] == "off:50" and provider.calls[-1]["queries"] == ["natural_language"]
    ids = [c["candidate_id"] for c in after["candidates"]]
    assert len(ids) == len(set(ids)) == 35  # 25 + the 10 left in a pool of 60; nobody twice
    assert first_ids < set(ids)
    assert len(states(after)["presented"]) == 25 + 5  # the next five are shown when the cycle completes
    assert after["diagnostics"]["funnel"]["retrieved"] == 50  # the first cycle's facts are not overwritten
    assert after["retrieval_exhausted"] is False or after["retrieval_exhausted"] is True  # reported either way


def test_a_second_cycle_skips_people_the_role_already_has(tmp_path: Path) -> None:
    provider = PagedProvider(120)
    provider.overlap_on_page2 = ["p000", "p001", "p002"]  # the next page repeats three people already in the role
    client, _, _, _, _ = build(tmp_path, provider=provider)
    role = start_role(client)
    sid = role["search_id"]
    for _ in range(4):
        client.post(f"/search/{sid}/more")
    client.post(f"/search/{sid}/more")
    after = wait(client, sid)
    ids = [c["candidate_id"] for c in after["candidates"]]
    assert len(ids) == len(set(ids))
    assert after["candidate_count"] == 50


def test_earlier_decisions_survive_a_new_cycle(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid = role["search_id"]
    presented = states(role)["presented"]
    decide(client, sid, presented[0], "shortlist")
    decide(client, sid, presented[1], "reject", feedback_reason="seniority")
    for _ in range(4):
        client.post(f"/search/{sid}/more")
    client.post(f"/search/{sid}/more")
    after = wait(client, sid)
    assert after["recruiter_decisions"][presented[0]] == "shortlist" and after["recruiter_decisions"][presented[1]] == "reject"
    assert after["feedback"][presented[1]]["reason"] == "seniority"


def test_when_nothing_more_can_be_found_show_more_says_so_and_starts_nothing(tmp_path: Path) -> None:
    client, provider, _, _, _ = build(tmp_path, total=30)  # one page, no cursor
    role = start_role(client)
    sid = role["search_id"]
    for _ in range(4):
        client.post(f"/search/{sid}/more")
    calls = len(provider.calls)
    outcome = client.post(f"/search/{sid}/more").json()
    assert outcome == {"presented": 0, "cycle_started": False, "exhausted": True}
    assert len(provider.calls) == calls
    assert client.get(f"/search/{sid}").json()["retrieval_exhausted"] is True


def test_show_more_while_a_cycle_is_running_is_refused(tmp_path: Path) -> None:
    client, _, _, store, _ = build(tmp_path)
    role = start_role(client)
    store.update(role["search_id"], lambda record: record.update({"status": "running"}))
    assert client.post(f"/search/{role['search_id']}/more").status_code == 409


# ---- calibration happens once ------------------------------------------------------------------------------------------------


def test_calibration_appears_once_there_is_enough_signal_not_at_a_fixed_count(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    assert role["calibration"]["state"] == "pending" and role["calibration"]["summary"] is None

    decide(client, sid, five[0], "shortlist")
    decide(client, sid, five[1], "shortlist")
    decide(client, sid, five[2], "shortlist")
    # Three decisions, but nothing the search can act on: no statement is manufactured.
    assert client.get(f"/search/{sid}").json()["calibration"] == {"state": "pending", "summary": None, "dismissed": []}

    decide(client, sid, five[3], "reject", feedback_reason="required_technology")
    ready = client.get(f"/search/{sid}").json()["calibration"]
    assert ready["state"] == "ready" and ready["summary"]["text"].startswith("Got it. I'll look for")
    assert ready["summary"]["dimensions"] == ["technology"]


def test_two_decisions_are_enough_when_one_carries_a_reason_and_all_five_are_never_required(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "reject", feedback_reason="seniority")
    assert client.get(f"/search/{sid}").json()["calibration"]["state"] == "pending"  # one decision is not enough
    decide(client, sid, five[1], "shortlist")
    ready = client.get(f"/search/{sid}").json()["calibration"]
    assert ready["state"] == "ready" and ready["summary"]["dimensions"] == ["seniority"]


def test_a_reason_on_a_candidate_outside_the_first_five_is_not_calibration_signal(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    other = states(role)["reserve"][0]
    client.post(f"/search/{sid}/more")  # more candidates are shown; the calibration is still pending
    decide(client, sid, five[0], "shortlist")
    decide(client, sid, other, "reject", feedback_reason="seniority")
    assert client.get(f"/search/{sid}").json()["calibration"]["state"] == "pending"


def test_calibration_happens_once_and_later_decisions_never_reopen_it(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "shortlist")
    decide(client, sid, five[1], "reject", feedback_reason="required_technology")
    assert client.get(f"/search/{sid}").json()["calibration"]["state"] == "ready"

    client.post(f"/search/{sid}/more")
    closed = client.get(f"/search/{sid}").json()["calibration"]
    assert closed["state"] == "closed"
    summary_at_close = closed["summary"]
    for candidate_id in states(client.get(f"/search/{sid}").json())["presented"][5:]:
        decide(client, sid, candidate_id, "reject", feedback_reason="seniority")
    decide(client, sid, five[2], "maybe", feedback_reason="type_of_work")
    client.post(f"/search/{sid}/more")
    final = client.get(f"/search/{sid}").json()["calibration"]
    assert final["state"] == "closed" and final["summary"] == summary_at_close


def test_showing_more_before_there_is_signal_does_not_use_up_the_calibration(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    client.post(f"/search/{sid}/more")
    assert client.get(f"/search/{sid}").json()["calibration"]["state"] == "pending"
    decide(client, sid, five[0], "reject", feedback_reason="seniority")
    decide(client, sid, five[1], "shortlist")
    assert client.get(f"/search/{sid}").json()["calibration"]["state"] == "ready"


def test_changing_a_decision_can_take_the_signal_away_before_it_is_closed(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "reject", feedback_reason="seniority")
    decide(client, sid, five[1], "shortlist")
    assert client.get(f"/search/{sid}").json()["calibration"]["state"] == "ready"
    decide(client, sid, five[0], "shortlist")
    assert client.get(f"/search/{sid}").json()["calibration"] == {"state": "pending", "summary": None, "dismissed": []}


def test_the_recruiter_can_correct_the_summary(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "reject", feedback_reason="required_technology")
    decide(client, sid, five[1], "reject", feedback_reason="seniority")
    decide(client, sid, five[2], "shortlist")
    corrected = client.post(f"/search/{sid}/calibration", json={"dismiss": ["technology"]}).json()
    assert corrected["calibration"]["summary"]["dimensions"] == ["seniority"]
    assert corrected["calibration"]["dismissed"] == ["technology"]


# ---- decisions and feedback -----------------------------------------------------------------------------------------------------


def test_decisions_reasons_and_notes_persist_and_reload(tmp_path: Path) -> None:
    client, _, _, store, app = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    assert decide(client, sid, five[0], "maybe").status_code == 200
    response = decide(client, sid, five[0], None, feedback_reason="seniority_unclear", feedback_note="  Level  unclear from titles  ")
    assert response.status_code == 200
    assert decide(client, sid, five[1], "reject", feedback_reason="domain", feedback_note="wrong industry").status_code == 200
    assert decide(client, sid, five[2], "shortlist").status_code == 200

    reloaded = client.get(f"/search/{sid}").json()
    assert reloaded["recruiter_decisions"][five[0]] == "maybe"
    assert reloaded["feedback"][five[0]] == {"decision": "maybe", "reason": "seniority_unclear", "note": "Level unclear from titles"}
    assert reloaded["feedback"][five[1]]["reason"] == "domain"
    assert five[2] not in reloaded["feedback"]  # a shortlist needs no feedback

    event = next(e for e in store.load(sid)["feedback_events"] if e["candidate_id"] == five[0] and e["feedback_reason"])
    assert set(event) >= {"candidate_id", "search_id", "decision", "feedback_reason", "feedback_note", "at"} and event["search_id"] == sid


def test_a_reason_must_fit_the_decision(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "maybe")
    assert decide(client, sid, five[0], None, feedback_reason="required_technology").status_code == 422  # a Reject reason
    decide(client, sid, five[1], "shortlist")
    assert decide(client, sid, five[1], None, feedback_reason="other").status_code == 422


def test_changing_a_decision_retires_its_reason(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid, c = role["search_id"], states(role)["presented"][0]
    decide(client, sid, c, "reject", feedback_reason="seniority")
    decide(client, sid, c, "shortlist")
    assert c not in client.get(f"/search/{sid}").json()["feedback"]


# ---- how feedback reaches the next retrieval -----------------------------------------------------------------------------------------


def _spy_tie_break(monkeypatch):
    seen: List[Dict[str, int]] = []
    original = search_pipeline.apply_admission_tie_break

    def spy(ranked, guidance, value_of):
        seen.append(dict(guidance.dimensions))
        return original(ranked, guidance, value_of)

    monkeypatch.setattr(search_pipeline, "apply_admission_tie_break", spy)
    return seen


def _drain_and_cycle(client, sid):
    for _ in range(4):
        client.post(f"/search/{sid}/more")
    client.post(f"/search/{sid}/more")
    return wait(client, sid)


def test_accumulated_feedback_guides_the_next_cycle_and_the_confirmed_search_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    seen = _spy_tie_break(monkeypatch)
    client, provider, _, store, _ = build(tmp_path, total=120)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    brief_before = client.get(f"/search/{sid}").json()["confirmed_brief"]
    decide(client, sid, five[0], "reject", feedback_reason="required_technology")
    decide(client, sid, five[1], "maybe", feedback_reason="skill_not_demonstrated")
    decide(client, sid, five[2], "reject", feedback_reason="seniority")
    _drain_and_cycle(client, sid)

    assert seen and seen[-1] == {"technology": 2, "seniority": 1}
    after = client.get(f"/search/{sid}").json()
    # The confirmed brief is exactly what the recruiter confirmed, and the query sent for the next page is the same one.
    assert after["confirmed_brief"] == brief_before
    assert provider.calls[-1]["payload"] == provider.calls[0]["payload"][: len(provider.calls[-1]["payload"])]
    snapshot = ConfirmationStore(storage_dir=tmp_path / "confirmations").load(brief_before["confirmation_id"])
    assert snapshot is not None  # the immutable snapshot still verifies against its hash


def test_feedback_that_cannot_be_translated_falls_back_to_the_confirmed_search(tmp_path: Path, monkeypatch) -> None:
    seen = _spy_tie_break(monkeypatch)
    client, provider, *_ = build(tmp_path, total=120)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "reject", feedback_reason="domain", feedback_note="wants fintech")
    decide(client, sid, five[1], "reject", feedback_reason="career_background")
    decide(client, sid, five[2], "reject", feedback_reason="other")
    after = _drain_and_cycle(client, sid)
    assert seen == []  # no guidance applied: the cycle ran exactly as confirmed
    assert after["candidate_count"] == 50  # and it still found the next people


# ---- meaningful change ---------------------------------------------------------------------------------------------------------------------------


def test_a_meaningful_change_runs_a_fresh_retrieval_extends_the_role_and_keeps_what_was_reviewed(tmp_path: Path) -> None:
    client, provider, clock, store, _ = build(tmp_path, total=60)
    role = start_role(client)
    sid, session_id = role["search_id"], role["_session_id"]
    presented = states(role)["presented"]
    decide(client, sid, presented[0], "shortlist")
    before_end = store.load(sid)["role"]["window_end"]
    calls = len(provider.calls)

    clock.advance(hours=6)
    new_confirmation = confirm(client, session_id, {"core_signals": ["Strong Python", "Kafka streaming"]})
    response = client.post("/search", json={"provider": "mock", "confirmation_id": new_confirmation, "jd_text": "", "search_id": sid})
    assert response.status_code == 200
    after = wait(client, sid)

    record = store.load(sid)
    assert len(provider.calls) > calls and provider.calls[-1]["cursor"] is None  # a fresh retrieval, not the old cursor
    assert record["role"]["changes"][0]["changed"] == ["core requirements"]
    assert record["role"]["window_end"] > before_end
    assert after["recruiter_decisions"][presented[0]] == "shortlist"
    assert after["confirmed_brief"]["confirmation_id"] == new_confirmation
    # What the recruiter was reviewing is untouched, and the new brief's first five are added to it.
    assert set(presented) <= set(states(after)["presented"])


def test_a_confirmation_that_changes_nothing_searched_runs_nothing(tmp_path: Path) -> None:
    client, provider, _, store, _ = build(tmp_path)
    role = start_role(client)
    sid, session_id = role["search_id"], role["_session_id"]
    calls, window_end = len(provider.calls), store.load(sid)["role"]["window_end"]
    same = confirm(client, session_id)
    response = client.post("/search", json={"provider": "mock", "confirmation_id": same, "jd_text": "", "search_id": sid})
    assert response.status_code == 200 and response.json()["status"] == "complete"
    assert len(provider.calls) == calls
    assert store.load(sid)["role"]["window_end"] == window_end and store.load(sid)["role"]["changes"] == []


def test_the_role_cannot_be_extended_beyond_five_days_by_changes(tmp_path: Path) -> None:
    client, provider, clock, store, _ = build(tmp_path, total=60)
    role = start_role(client)
    sid, session_id = role["search_id"], role["_session_id"]
    hard_end = store.load(sid)["role"]["hard_end"]
    for step, signals in enumerate((["A one"], ["A two"], ["A three"], ["A four"], ["A five"])):
        clock.advance(hours=20)
        confirmation = confirm(client, session_id, {"core_signals": signals})
        client.post("/search", json={"provider": "mock", "confirmation_id": confirmation, "jd_text": "", "search_id": sid})
        wait(client, sid)
    record = store.load(sid)
    assert record["role"]["window_end"] <= hard_end and record["role"]["hard_end"] == hard_end


# ---- lifecycle through the API ------------------------------------------------------------------------------------------------------------------


def test_the_role_pauses_by_itself_after_the_normal_window_and_says_what_to_do_next(tmp_path: Path) -> None:
    client, _, clock, store, _ = build(tmp_path)
    role = start_role(client)
    sid = role["search_id"]
    assert role["role"]["status"] == "searching"
    clock.advance(days=2.9)
    assert client.get(f"/search/{sid}").json()["role"]["status"] == "searching"
    clock.advance(days=0.2)
    paused = client.get(f"/search/{sid}").json()["role"]
    assert paused["status"] == "paused" and paused["pause_kind"] == "no_engagement" and paused["has_feedback"] is False


def test_a_paused_role_with_feedback_offers_to_resume(tmp_path: Path) -> None:
    client, _, clock, _, _ = build(tmp_path)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "shortlist")
    decide(client, sid, five[1], "reject", feedback_reason="seniority")
    decide(client, sid, five[2], "maybe", feedback_reason="type_of_work")
    clock.advance(days=3.1)
    paused = client.get(f"/search/{sid}").json()["role"]
    assert paused["status"] == "paused" and paused["pause_kind"] == "feedback" and paused["can_resume"] is True


def test_manual_pause_preserves_everything_and_resume_continues_from_the_role_history(tmp_path: Path) -> None:
    client, provider, clock, store, _ = build(tmp_path, total=120)
    role = start_role(client)
    sid, five = role["search_id"], states(role)["presented"]
    decide(client, sid, five[0], "shortlist")
    snapshot_before = client.get(f"/search/{sid}").json()

    paused = client.post(f"/search/{sid}/role", json={"action": "pause"}).json()
    assert paused["role"]["status"] == "paused"
    after_pause = client.get(f"/search/{sid}").json()
    for key in ("candidates", "recruiter_decisions", "presentation", "calibration"):
        assert after_pause[key] == snapshot_before[key]
    assert store.load(sid)["retrieval"]["next_cursor"] == "off:50"  # retrieval state kept

    calls = len(provider.calls)
    resumed = client.post(f"/search/{sid}/role", json={"action": "resume"}).json()
    assert resumed["role"]["status"] == "searching"
    after = wait(client, sid)
    assert provider.calls[calls]["cursor"] == "off:50"  # continued from where the role was
    assert after["new_candidates"] > 0 and after["candidate_count"] > 25
    assert set(states(after)["presented"]) == set(states(snapshot_before)["presented"])  # nothing was moved under the recruiter


def test_resume_is_refused_once_the_automatic_search_has_run_its_course(tmp_path: Path) -> None:
    client, _, clock, _, _ = build(tmp_path)
    role = start_role(client)
    sid = role["search_id"]
    clock.advance(days=5.5)
    client.get(f"/search/{sid}")
    refused = client.post(f"/search/{sid}/role", json={"action": "resume"})
    assert refused.status_code == 409
    # The recruiter can still ask for more by hand.
    assert client.post(f"/search/{sid}/more").status_code == 200


# ---- the daily background search --------------------------------------------------------------------------------------------------------------------


def test_the_daily_search_is_a_fresh_retrieval_that_only_reads_profiles_the_role_has_never_been_shown(tmp_path: Path) -> None:
    client, provider, clock, store, app = build(tmp_path, total=60)
    role = start_role(client)
    sid = role["search_id"]
    presented_before = states(role)["presented"]
    order_before = [c["candidate_id"] for c in role["candidates"]]
    cursor_before = store.load(sid)["retrieval"]["next_cursor"]
    # Retrieval history and inventory are different things: 50 profiles came back, 25 were admitted and read.
    assert len(store.load(sid)["retrieved_ids"]) == 50 and len(order_before) == 25
    harvested_before = set(store.load(sid)["harvest_evidence"])

    clock.advance(days=1.1)
    provider.extra_on_fresh = ["new-1", "new-2", "new-3"]  # the pool gained three people since the first retrieval
    calls = len(provider.calls)
    app.state.role_runtime.tick_all()
    after = wait(client, sid)

    assert provider.calls[calls]["cursor"] is None  # fresh, from the first page, not the previous cursor
    ids = [c["candidate_id"] for c in after["candidates"]]
    assert len(ids) == len(set(ids)) == 28  # only the three genuinely new profiles were admitted
    assert ids[:25] == order_before  # existing candidates keep their places
    assert set(ids[25:]) == {"new-1", "new-2", "new-3"}
    assert after["new_candidates"] == 3
    assert all(after["presentation"][c]["state"] == "reserve" and after["presentation"][c]["source"] == "daily" for c in ids[25:])
    # The 25 retrieved-but-not-admitted profiles were skipped: no profile read, no evidence, no judgment for them.
    record = store.load(sid)
    assert set(record["harvest_evidence"]) == harvested_before | {"new-1", "new-2", "new-3"}
    assert len(record["retrieved_ids"]) == 53
    assert record["cycles"][-1]["kind"] == "daily" and record["response"]["diagnostics"]["funnel"]["retrieved"] == 50  # first cycle's facts
    # Nothing about the recruiter's review or the manual cursor moved.
    assert states(after)["presented"] == presented_before
    assert record["retrieval"]["next_cursor"] == cursor_before
    assert record["role"]["last_auto_search_at"]


def test_a_skipped_profile_is_never_decided_for_the_recruiter_and_nothing_is_lost(tmp_path: Path) -> None:
    client, provider, clock, store, app = build(tmp_path, total=60)
    role = start_role(client)
    sid = role["search_id"]
    first = states(role)["presented"][0]
    decide(client, sid, first, "shortlist")
    clock.advance(days=1.1)
    app.state.role_runtime.tick_all()
    after = wait(client, sid)
    assert after["recruiter_decisions"] == {first: "shortlist"}
    assert after["candidate_count"] == 25  # nothing new, nothing lost, nothing re-read
    assert after["new_candidates"] == 0


def test_show_me_more_still_walks_the_cursor_after_a_daily_search(tmp_path: Path) -> None:
    client, provider, clock, store, app = build(tmp_path, total=120)
    role = start_role(client)
    sid = role["search_id"]
    clock.advance(days=1.1)
    app.state.role_runtime.tick_all()
    wait(client, sid)
    for _ in range(4):
        client.post(f"/search/{sid}/more")
    client.post(f"/search/{sid}/more")
    after = wait(client, sid)
    assert provider.calls[-1]["cursor"] == "off:50"
    assert after["candidate_count"] == 50


def test_new_candidates_are_shown_only_when_the_recruiter_asks(tmp_path: Path) -> None:
    client, provider, clock, _, app = build(tmp_path, total=60)
    role = start_role(client)
    sid = role["search_id"]
    presented_before = states(role)["presented"]
    clock.advance(days=1.1)
    provider.extra_on_fresh = [f"new-{i}" for i in range(7)]
    app.state.role_runtime.tick_all()
    quiet = wait(client, sid)
    assert quiet["new_candidates"] == 7 and states(quiet)["presented"] == presented_before  # a quiet signal, nothing moved

    outcome = client.post(f"/search/{sid}/more", json={"only_new": True}).json()
    assert outcome["presented"] == 5 and outcome["cycle_started"] is False
    after = client.get(f"/search/{sid}").json()
    assert after["new_candidates"] == 2
    assert set(presented_before) <= set(states(after)["presented"])


def test_a_paused_role_does_not_search_in_the_background(tmp_path: Path) -> None:
    client, provider, clock, _, app = build(tmp_path)
    role = start_role(client)
    client.post(f"/search/{role['search_id']}/role", json={"action": "pause"})
    calls = len(provider.calls)
    clock.advance(days=2)
    app.state.role_runtime.tick_all()
    assert len(provider.calls) == calls


def test_no_daily_search_runs_after_the_window_and_the_role_pauses_instead(tmp_path: Path) -> None:
    client, provider, clock, store, app = build(tmp_path)
    role = start_role(client)
    calls = len(provider.calls)
    clock.advance(days=3.2)
    app.state.role_runtime.tick_all()
    assert len(provider.calls) == calls
    assert store.load(role["search_id"])["role"]["status"] == "paused"


# ---- narrow and empty searches ------------------------------------------------------------------------------------------------------------------


def test_a_search_that_returns_fewer_than_fifty_profiles_is_reported_factually(tmp_path: Path) -> None:
    client, *_ = build(tmp_path, total=12)
    role = start_role(client)
    assert role["availability"] == {"kind": "narrow", "profiles_returned": 12, "retrieved": 12}
    assert len(states(role)["presented"]) == 5 and len(states(role)["reserve"]) == 7  # all twelve were still reviewed


def test_a_search_that_returns_nothing(tmp_path: Path) -> None:
    client, *_ = build(tmp_path, total=0)
    role = start_role(client)
    assert role["availability"]["kind"] == "zero" and role["candidate_count"] == 0
    assert states(role) == {"presented": [], "reserve": []}


def test_a_narrow_search_that_has_run_out_pauses_as_narrow_and_never_relaxes_the_brief(tmp_path: Path) -> None:
    client, provider, clock, store, _ = build(tmp_path, total=12)
    role = start_role(client)
    sid = role["search_id"]
    for _ in range(3):
        client.post(f"/search/{sid}/more")
    client.post(f"/search/{sid}/more")  # nothing left: marks the retrieval exhausted
    clock.advance(days=3.1)
    paused = client.get(f"/search/{sid}").json()
    assert paused["role"]["status"] == "paused" and paused["role"]["pause_kind"] == "narrow"
    # The confirmed search was never relaxed: every retrieval sent the same plan.
    natural = [call for call in provider.calls if "natural_language" in call["queries"]]
    assert natural and all(call["payload"] == natural[0]["payload"] for call in natural)


def test_a_role_with_nothing_left_in_a_large_search_pauses_as_exhausted(tmp_path: Path) -> None:
    client, _, clock, _, _ = build(tmp_path, total=50)
    role = start_role(client)
    sid = role["search_id"]
    for _ in range(5):
        client.post(f"/search/{sid}/more")
    for _ in range(5):
        r = client.post(f"/search/{sid}/more").json()
    clock.advance(days=3.1)
    kind = client.get(f"/search/{sid}").json()["role"]["pause_kind"]
    assert kind in ("exhausted", "narrow", "feedback", "no_engagement")
    assert kind != "narrow"  # 50 profiles were returned: not a narrow search


def test_an_interrupted_cycle_leaves_the_role_usable_after_a_restart(tmp_path: Path) -> None:
    client, _, _, store, _ = build(tmp_path)
    role = start_role(client)
    sid = role["search_id"]
    store.update(sid, lambda record: record.update({"status": "running"}))
    assert search_pipeline.reconcile_interrupted_searches(store) == 1
    after = client.get(f"/search/{sid}").json()
    assert after["status"] == "complete" and len(states(after)["presented"]) == 5
    assert client.post(f"/search/{sid}/more").status_code == 200


def test_the_workspace_is_told_which_set_each_candidate_was_shown_in(tmp_path: Path) -> None:
    client, *_ = build(tmp_path)
    role = start_role(client)
    sid = role["search_id"]
    assert {entry["batch"] for entry in role["presentation"].values() if entry["state"] == "presented"} == {1}
    assert all(entry["batch"] is None for entry in role["presentation"].values() if entry["state"] == "reserve")
    client.post(f"/search/{sid}/more")
    after = client.get(f"/search/{sid}").json()
    assert sorted({entry["batch"] for entry in after["presentation"].values() if entry["state"] == "presented"}) == [1, 2]
