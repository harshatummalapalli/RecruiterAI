"""The confirmation gate: the browser is never the source of the executable search intent."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.providers.registry import ProviderRegistry
from backend.services.confirmation import ConfirmationStore, location_override_for_search
from backend.services.intake_reasoning import IntakeReasoner
from backend.services.intake_session import IntakeSessionManager
from backend.services.search_store import SearchStore
from tests.test_api import PlanCapturingProvider, _login, _wait_for_search
from tests.test_intake_api import NYC_BOUNDARY, _QueuedFakeClient
from tests.test_intake_pinning import EXPERIENCE_ASK, KAFKA_ASK, PATCH_KAFKA, PATCH_YEARS, RAW, TASK_A, TASK_B
from tests.test_intake_reasoning import CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _app(tmp_path: Path, payloads, provider=None, require_confirmation: bool = True):
    from backend.services.candidate_merger import CandidateMerger
    from backend.services.candidate_ranker import CandidateRanker
    from backend.services.capability_mapper import CapabilityMapper
    from backend.services.match_explainer import MatchExplainer
    from backend.services.query_expansion import QueryExpansionService
    from backend.services.search_diagnostics import SearchDiagnostics
    from backend.services.search_planner import SearchPlanner

    ProviderRegistry._providers.clear()
    provider = provider or PlanCapturingProvider()
    ProviderRegistry.register("mock", provider)
    manager = IntakeSessionManager(
        reasoner=IntakeReasoner(client=_QueuedFakeClient(payloads)),
        store=SearchStore(storage_dir=tmp_path / "sessions"),
    )
    app = create_app(
        search_store=SearchStore(storage_dir=tmp_path / "searches"),
        intake_session_manager=manager,
        confirmation_store=ConfirmationStore(storage_dir=tmp_path / "confirmations"),
        provider_registry=ProviderRegistry,
        require_confirmation=require_confirmation,
    )
    client = TestClient(app)
    _login(client)
    return client, provider


CLEAR = [(CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B)]


def _start(client: TestClient, raw: str = "Senior Backend Engineer, Python.", **extra: Any) -> Dict[str, Any]:
    return client.post("/intake/start", json={"raw_input": raw, "boundary": NYC_BOUNDARY, **extra}).json()


def _run(client: TestClient, confirmation_id: str, **extra: Any) -> Dict[str, Any]:
    """POST /search from a confirmation and wait for the background pipeline, so provider calls can be inspected."""
    response = client.post("/search", json={"provider": "mock", "confirmation_id": confirmation_id, "jd_text": "", **extra})
    assert response.status_code == 200, response.text
    return _wait_for_search(client, response.json()["search_id"])


def _confirm(client: TestClient, session_id: str, edits: Dict[str, Any] | None = None):
    return client.post(f"/intake/{session_id}/confirmations", json={"edits": edits or {}})


# ---- the gate ---------------------------------------------------------------------------------------------------


def test_a_ready_brief_becomes_an_immutable_snapshot_and_a_search_runs_only_from_it(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, CLEAR)
    started = _start(client)
    confirmed = _confirm(client, started["session_id"])
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["candidate_identity"] == "Senior Backend Engineer" and body["content_hash"]

    response = client.post("/search", json={"provider": "mock", "confirmation_id": body["confirmation_id"], "jd_text": "ignored"})
    assert response.status_code == 200
    finished = _wait_for_search(client, response.json()["search_id"])
    assert finished["status"] == "complete"
    # The workspace can name the role after a reload without any browser state.
    assert finished["confirmed_brief"]["confirmation_id"] == body["confirmation_id"]
    assert finished["confirmed_brief"]["posted_title"] is None or isinstance(finished["confirmed_brief"]["posted_title"], str)
    assert finished["confirmed_brief"]["candidate_identity"] == "Senior Backend Engineer"
    assert provider.seen_plans, "the provider was searched"


def test_search_without_a_confirmation_is_refused_when_confirmation_is_required(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, CLEAR)
    no_confirmation = client.post("/search", json={"provider": "mock", "jd_text": "Need a Python engineer"})
    assert no_confirmation.status_code == 409
    assert provider.seen_plans == []


def test_a_client_supplied_intent_is_refused_without_a_valid_confirmation(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, CLEAR)
    forged = {"provider": "mock", "jd_text": "x", "intent": {"role": {"title": "Anything I like"}, "location": {"countries": ["Nowhere"]}}}
    assert client.post("/search", json=forged).status_code == 409
    assert client.post("/search", json={**forged, "confirmation_id": "not-a-real-id"}).status_code == 422
    assert provider.seen_plans == []


def test_a_confirmed_search_cannot_also_carry_its_own_intent_or_location(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, CLEAR)
    confirmation_id = _confirm(client, _start(client)["session_id"]).json()["confirmation_id"]
    base = {"provider": "mock", "confirmation_id": confirmation_id, "jd_text": "x"}
    assert client.post("/search", json={**base, "intent": {"role": {"title": "Hijacked"}}}).status_code == 422
    assert client.post("/search", json={**base, "location": {"countries": ["Elsewhere"]}}).status_code == 422
    assert provider.seen_plans == []


def test_the_search_runs_the_snapshot_not_what_the_browser_says(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, CLEAR)
    confirmation_id = _confirm(client, _start(client)["session_id"]).json()["confirmation_id"]
    _run(client, confirmation_id, jd_text="totally different words")
    text = json.dumps([query.model_dump() if hasattr(query, "model_dump") else vars(query) for query in provider.seen_plans[0].searches], default=str)
    assert "New York" in text and "Senior Backend Engineer" in text
    assert "totally different words" not in text


def test_a_tampered_snapshot_is_treated_as_invalid(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, CLEAR)
    confirmation_id = _confirm(client, _start(client)["session_id"]).json()["confirmation_id"]
    path = tmp_path / "confirmations" / f"{confirmation_id}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["search_intent"]["role"]["title"] = "Someone else entirely"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert client.post("/search", json={"provider": "mock", "confirmation_id": confirmation_id}).status_code == 422
    assert provider.seen_plans == []


def test_the_legacy_path_still_works_when_confirmation_is_not_required(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, CLEAR, require_confirmation=False)
    legacy = client.post("/search", json={"provider": "mock", "jd_text": "x", "intent": {"role": {"title": "Python Engineer"}}})
    assert legacy.status_code == 200
    _wait_for_search(client, legacy.json()["search_id"])
    assert provider.seen_plans


# ---- what blocks confirmation -----------------------------------------------------------------------------------


def test_a_pending_question_blocks_confirmation_with_a_plain_reason(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, [(TASK_A, TASK_B)])
    started = _start(client, RAW)
    assert started["result"]["status"] == "needs_clarification"
    refused = _confirm(client, started["session_id"])
    assert refused.status_code == 409
    assert any("2 questions still need your answer" in reason for reason in refused.json()["detail"]["reasons"])


def test_zero_core_requirements_and_a_narrow_search_do_not_block_confirmation(tmp_path: Path) -> None:
    empty_b = dict(CLEAR_ROLE_TASK_B, final_search_intent=dict(CLEAR_ROLE_TASK_B["final_search_intent"], hard_requirements=[]))
    client, _ = _app(tmp_path, [(CLEAR_ROLE_TASK_A, empty_b)])
    assert _confirm(client, _start(client)["session_id"]).status_code == 200


def test_a_session_without_a_valid_boundary_cannot_be_confirmed(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, CLEAR)
    started = _start(client)
    path = tmp_path / "sessions" / f"{started['session_id']}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["boundary"] = None  # e.g. a session stored before boundaries were mandatory
    path.write_text(json.dumps(record), encoding="utf-8")
    refused = _confirm(client, started["session_id"])
    assert refused.status_code == 409 and any("boundary" in r.lower() for r in refused.json()["detail"]["reasons"])


def test_answering_the_questions_then_confirming_uses_the_confirmed_answers(tmp_path: Path) -> None:
    client, provider = _app(tmp_path, [(TASK_A, TASK_B), (PATCH_YEARS, PATCH_KAFKA)])
    started = _start(client, RAW)
    ids = {i["issue"]: i["id"] for i in started["result"]["decision"]["issues"]}
    client.post(f"/intake/{started['session_id']}/answer", json={"issue_id": ids["Conflicting experience ranges"], "value": "8to10", "label": "8-10 years"})
    done = client.post(f"/intake/{started['session_id']}/answer", json={"issue_id": ids["Kafka requirement level"], "value": "nice", "label": "Nice-to-have"}).json()
    assert done["result"]["status"] == "ready"
    body = _confirm(client, started["session_id"]).json()
    assert body["search_intent"]["experience"] == {"minimum_years": 8, "maximum_years": 10, "confidence_score": None}
    assert "Kafka" in body["search_intent"]["differentiator_signals"] and "Kafka" not in body["search_intent"]["core_signals"]


# ---- determinism ------------------------------------------------------------------------------------------------


def test_the_same_confirmed_inputs_give_the_same_content_hash_but_distinct_confirmations(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, CLEAR + CLEAR)
    first = _confirm(client, _start(client)["session_id"]).json()
    second = _confirm(client, _start(client)["session_id"]).json()
    assert first["confirmation_id"] != second["confirmation_id"]
    # Two different sessions have different raw ids but identical content, so the executable intent is identical.
    assert first["search_intent"] == second["search_intent"]
    assert first["content_hash"] == second["content_hash"]


# ---- edits are a whitelist --------------------------------------------------------------------------------------


def test_recruiter_edits_are_applied_by_the_server_through_a_whitelist(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, CLEAR)
    session_id = _start(client)["session_id"]
    edits = {
        "candidate_identity": "Platform Engineer",
        "include_titles": ["SRE", "  SRE ", "Infrastructure Engineer"],
        "exclude_titles": ["Intern"],
        "minimum_years": 6,
        "core_signals": ["Kubernetes operations"],
    }
    body = _confirm(client, session_id, edits).json()
    intent = body["search_intent"]
    assert intent["role"]["title"] == "Platform Engineer"
    assert intent["titles"]["include_titles"] == ["SRE", "Infrastructure Engineer"]  # trimmed and de-duplicated
    assert intent["titles"]["exclude_titles"] == ["Intern"]
    assert intent["experience"]["minimum_years"] == 6
    assert intent["core_signals"] == ["Kubernetes operations"]
    # Edited requirements rebuild the search sentence from what is on screen, so it is never stale.
    assert "Kubernetes operations" in intent["natural_language_search_query"]
    assert body["edits"]["candidate_identity"] == "Platform Engineer"


def test_location_and_work_mode_cannot_be_edited_only_the_boundary_can(tmp_path: Path) -> None:
    client, _ = _app(tmp_path, CLEAR)
    session_id = _start(client)["session_id"]
    for forbidden in ({"location": {"countries": ["France"]}}, {"country": "France"}, {"work_mode": "remote"}, {"hiring_company": "Other"}):
        assert _confirm(client, session_id, forbidden).status_code == 422


def test_an_unchanged_confirmation_carries_the_posted_title_and_the_identity_separately(tmp_path: Path) -> None:
    task_a = dict(CLEAR_ROLE_TASK_A, primary_candidate_identity={"value": "Backend-heavy AI Engineer", "source": "inferred"})
    client, _ = _app(tmp_path, [(task_a, CLEAR_ROLE_TASK_B)])
    started = _start(client, "AI Engineer\nBackend work in Python.", posted_title="AI Engineer")
    body = _confirm(client, started["session_id"]).json()
    assert body["posted_title"] == "AI Engineer" and body["posted_title_source"] == "recruiter"
    assert body["candidate_identity"] == "Backend-heavy AI Engineer"
    assert body["search_intent"]["role"]["posted_title"] == "AI Engineer"
    assert body["search_intent"]["role"]["title"] == "Backend-heavy AI Engineer"


# ---- retrieval parity: the location the search filters on is what the browser used to send ----------------------


def _intent(**location: Any):
    from backend.models.search_intent import Location, Role, SearchIntent

    return SearchIntent(role=Role(title="Engineer"), location=Location(**location))


def test_a_single_city_with_a_radius_is_a_radius_search_anchored_on_city_and_state() -> None:
    override = location_override_for_search(_intent(countries=["Canada"], states=["Ontario"], cities=["Toronto"], radius_miles=25.0, work_mode="hybrid"))
    assert override["search_geography"] == "radius"
    assert (override["countries"], override["states"], override["cities"]) == (["Canada"], ["Ontario"], ["Toronto"])
    assert (override["radius_miles"], override["radius_place"], override["work_mode"]) == (25.0, "Toronto, Ontario", "hybrid")


def test_remote_anywhere_is_a_country_search_with_no_city_or_state() -> None:
    override = location_override_for_search(_intent(countries=["Canada"], work_mode="remote"))
    assert override["search_geography"] == "country"
    assert (override["countries"], override["states"], override["cities"], override["radius_miles"]) == (["Canada"], [], [], None)


def test_remote_states_and_remote_cities_are_lists_without_a_radius() -> None:
    states = location_override_for_search(_intent(countries=["United States"], states=["Texas", "California"], work_mode="remote"))
    assert (states["search_geography"], states["states"], states["cities"], states["radius_miles"]) == ("multiple", ["Texas", "California"], [], None)
    cities = location_override_for_search(_intent(countries=["United States"], cities=["Austin", "Denver"], work_mode="remote"))
    assert (cities["cities"], cities["states"], cities["radius_place"]) == (["Austin", "Denver"], [], None)


def test_the_model_written_search_sentence_is_not_sent_to_retrieval_by_default(tmp_path: Path, monkeypatch) -> None:
    # The browser has never sent it, so it has never reached the provider. Sending it would change retrieval.
    client, provider = _app(tmp_path, CLEAR)
    confirmation_id = _confirm(client, _start(client)["session_id"]).json()["confirmation_id"]
    stored = json.loads((tmp_path / "confirmations" / f"{confirmation_id}.json").read_text(encoding="utf-8"))
    assert stored["search_intent"]["natural_language_search_query"]  # kept in the snapshot for the record
    _run(client, confirmation_id)
    natural = next(q for q in provider.seen_plans[0].searches if q.query_name == "natural_language")
    assert "backend engineer with strong Python" not in json.dumps(natural.model_dump(), default=str).lower().replace("  ", " ")


def test_the_sentence_reaches_retrieval_only_when_explicitly_switched_on(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RECRUITERAI_SEND_CONFIRMED_SEARCH_SENTENCE", "true")
    client, provider = _app(tmp_path, CLEAR)
    confirmation_id = _confirm(client, _start(client)["session_id"]).json()["confirmation_id"]
    _run(client, confirmation_id)
    natural = next(q for q in provider.seen_plans[0].searches if q.query_name == "natural_language")
    assert "strong python" in json.dumps(natural.model_dump(), default=str).lower()
