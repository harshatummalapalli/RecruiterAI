"""Posted title (what the role was called) and candidate identity (what to search for) are separate, always."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.models.intake import FieldValue, RoleUnderstanding
from backend.services.intake_reasoning import IntakeReasoner, apply_posted_title
from tests.test_intake_api import NYC_BOUNDARY, _app_with_intake, _login
from tests.test_intake_reasoning import CLEAR_ROLE_TASK_A, CLEAR_ROLE_TASK_B, FakeOpenAIClient

JD = "AI Engineer\nNorthwind Payments is hiring. About 70% backend engineering in Python."


def _understanding(posted: str | None) -> RoleUnderstanding:
    return RoleUnderstanding(posted_title=posted, primary_candidate_identity=FieldValue(value="Backend-heavy AI Engineer"))


def test_a_recruiter_typed_title_is_kept_verbatim() -> None:
    understanding = _understanding("Something the model made up")
    apply_posted_title(understanding, JD, "  AI Engineer (Platform)  ")
    assert understanding.posted_title == "AI Engineer (Platform)"  # whitespace trimmed, nothing else changed
    assert understanding.posted_title_source == "recruiter"


def test_a_title_read_from_the_jd_is_kept_only_when_it_appears_in_the_text() -> None:
    found = _understanding("AI Engineer")
    apply_posted_title(found, JD, None)
    assert (found.posted_title, found.posted_title_source) == ("AI Engineer", "jd")

    # Case and punctuation differences do not matter, but the words must really be there.
    loose = _understanding("ai  engineer!")
    apply_posted_title(loose, JD, "")
    assert loose.posted_title_source == "jd"


def test_an_invented_title_is_dropped_rather_than_shown_as_posted() -> None:
    made_up = _understanding("Principal Machine Learning Architect")
    apply_posted_title(made_up, JD, None)
    assert made_up.posted_title is None and made_up.posted_title_source is None

    none_at_all = _understanding(None)
    apply_posted_title(none_at_all, JD, None)
    assert none_at_all.posted_title is None


def test_the_recruiter_title_reaches_task_a_and_survives_to_the_search_intent(tmp_path: Path) -> None:
    task_a = dict(CLEAR_ROLE_TASK_A, posted_title="Totally different", primary_candidate_identity={"value": "Backend-heavy AI Engineer", "source": "inferred"})
    client = TestClient(_app_with_intake(tmp_path, [(task_a, CLEAR_ROLE_TASK_B)]))
    _login(client)

    started = client.post("/intake/start", json={"raw_input": JD, "boundary": NYC_BOUNDARY, "posted_title": "AI Engineer"}).json()
    role = started["result"]["role_understanding"]
    assert role["posted_title"] == "AI Engineer" and role["posted_title_source"] == "recruiter"
    assert role["primary_candidate_identity"]["value"] == "Backend-heavy AI Engineer"

    intent = client.post(f"/intake/{started['session_id']}/confirm").json()
    assert intent["role"]["posted_title"] == "AI Engineer"
    assert intent["role"]["posted_title_source"] == "recruiter"
    # The candidate identity drives the search; the posted title never replaces it.
    assert intent["role"]["title"] == "Backend-heavy AI Engineer"


def test_the_posted_title_is_told_to_task_a() -> None:
    prompt = IntakeReasoner._task_a_user_prompt(JD, " AI Engineer ")
    assert 'exactly: "AI Engineer"' in prompt
    assert "posted title" not in IntakeReasoner._task_a_user_prompt(JD, None)


def test_the_source_of_the_title_survives_a_session_reload(tmp_path: Path) -> None:
    task_a = dict(CLEAR_ROLE_TASK_A, posted_title="AI Engineer")
    client = TestClient(_app_with_intake(tmp_path, [(task_a, CLEAR_ROLE_TASK_B)]))
    _login(client)
    started = client.post("/intake/start", json={"raw_input": JD, "boundary": NYC_BOUNDARY}).json()
    assert started["result"]["role_understanding"]["posted_title_source"] == "jd"
    # A fresh manager reading the same stored session sees the same thing.
    from backend.services.intake_session import IntakeSessionManager
    from backend.services.search_store import SearchStore

    reloaded = IntakeSessionManager(store=SearchStore(storage_dir=tmp_path / "intake_sessions")).get(started["session_id"])
    assert (reloaded.result.role_understanding.posted_title, reloaded.result.role_understanding.posted_title_source) == ("AI Engineer", "jd")
