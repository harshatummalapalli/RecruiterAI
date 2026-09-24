"""The CrustData Structured Search Playground: catalog integrity and honesty about our account, exact Boolean
construction (the brief's nested examples), verbatim values, all_of rules, and a safe local server. None of it
touches production search."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.experiments.crustdata_retrieval.structured import VERIFIED_FILTER_FIELDS
from backend.experiments.structured_playground import runner
from backend.experiments.structured_playground.builder import build
from backend.experiments.structured_playground.catalog import (
    BY_NAME,
    CATALOG,
    DOCUMENTED_PATHS,
    NOT_DOCUMENTED_IN_PEOPLE_SEARCH,
    OPERATORS,
    UNSUPPORTED_REQUESTS,
    catalog_payload,
)
from backend.experiments.structured_playground.server import create_app
from backend.services.search_store import SearchStore

TITLE = "experience.employment_details.current.title"


def cond(field, operator, values=None, **extra):
    return {"type": "condition", "field": field, "operator": operator, "values": values or [], **extra}


def group(op, *children):
    return {"type": "group", "op": op, "children": list(children)}


def leaf(field, operator, value):
    return {"field": field, "type": operator, "value": value}


# --- catalog -----------------------------------------------------------------------------------------------------------
def test_catalog_is_comprehensive_unique_and_fully_described() -> None:
    assert len(CATALOG) >= 150 and len({e["name"] for e in CATALOG}) == len(CATALOG) == len(DOCUMENTED_PATHS)
    required = {"name", "display_name", "category", "provider_field", "supported_operators", "value_type", "multi_value",
                "verified_in_our_account", "source", "notes"}
    for entry in CATALOG:
        assert required <= entry.keys()
        assert entry["provider_field"] == entry["name"]
        assert set(entry["supported_operators"]) <= set(OPERATORS)
        assert entry["verified_in_our_account"] in ("verified", "documented_unverified", "unavailable")
    categories = {e["category"] for e in CATALOG}
    assert {"PERSON", "PROFESSIONAL", "CURRENT EMPLOYMENT", "PAST EMPLOYMENT", "EDUCATION"} <= categories


def test_operator_vocabulary_matches_the_docs_including_the_traps() -> None:
    assert "=>" in OPERATORS and "=<" in OPERATORS
    assert ">=" not in OPERATORS and "<=" not in OPERATORS and "contains" not in OPERATORS


def test_green_fields_are_exactly_what_our_account_evidence_supports() -> None:
    green = {e["name"] for e in CATALOG if e["verified_in_our_account"] == "verified"}
    assert green == {
        "basic_profile.location.country", "basic_profile.location.state", "basic_profile.location.city", "basic_profile.location",
        TITLE, "experience.employment_details.past.title", "years_of_experience_raw",
        "experience.employment_details.current.company_name", "basic_profile.name",
    }
    # every filter production / EXP-001 emit is a catalog field, and none of them is marked unavailable
    for field in VERIFIED_FILTER_FIELDS:
        assert field in BY_NAME and BY_NAME[field]["verified_in_our_account"] != "unavailable"


def test_known_unavailable_things_are_red_and_never_converted_into_something_else() -> None:
    assert BY_NAME["years_of_experience"]["verified_in_our_account"] == "unavailable"
    assert BY_NAME["skills.professional_network_skills"]["verified_in_our_account"] == "unavailable"
    names = {u["name"] for u in UNSUPPORTED_REQUESTS}
    assert {"zip_code", "work_mode"} <= names
    assert "zip_code" not in BY_NAME and "work_mode" not in BY_NAME       # not selectable, not remapped to another field
    assert {"mentioned_in_news", "company_overview", "company_keyword"} <= {u["name"] for u in NOT_DOCUMENTED_IN_PEOPLE_SEARCH}
    assert not any("news" in e["name"] or "overview" in e["name"] for e in CATALOG)   # nothing invented


def test_closed_sets_and_gating_are_recorded() -> None:
    assert BY_NAME["experience.employment_details.current.seniority_level"]["allowed_values"][0] == "Entry Level"
    assert "myself only" in BY_NAME["experience.employment_details.current.company_headcount_range"]["allowed_values"]
    assert BY_NAME["skills.professional_network_skills"]["response_gated"] is True
    assert BY_NAME["years_of_experience_raw"]["value_type"] == "number"
    assert catalog_payload()["counts"]["verified"] == 9


# --- the brief's own examples --------------------------------------------------------------------------------------------
def test_title_group_or_becomes_exactly_that_or_group_with_values_verbatim() -> None:
    result = build(group("and", cond(TITLE, "(.)", ["Backend Engineer", "Platform Engineer", "Software Engineer"])))
    assert result["ok"]
    assert result["filters"] == {"op": "and", "conditions": [{"op": "or", "conditions": [
        leaf(TITLE, "(.)", "Backend Engineer"), leaf(TITLE, "(.)", "Platform Engineer"), leaf(TITLE, "(.)", "Software Engineer")]}]}


def test_three_or_groups_joined_by_and() -> None:
    skills, tech = "skills.professional_network_skills", "experience.employment_details.current.description"
    result = build(group("and",
        group("or", cond(TITLE, "(.)", ["Backend Engineer", "Platform Engineer", "Software Engineer"])),
        group("or", cond(skills, "(.)", ["Java", "Python"])),
        group("or", cond(tech, "(.)", ["LLM", "AI", "RAG"]))))
    assert result["ok"]
    top = result["filters"]
    assert top["op"] == "and" and [g["op"] for g in top["conditions"]] == ["or", "or", "or"]
    assert [len(g["conditions"][0]["conditions"]) for g in top["conditions"]] == [3, 2, 3]
    assert "AND" in result["boolean_text"] and result["boolean_text"].count("OR") >= 5


def test_nested_groups_to_arbitrary_depth() -> None:
    skills, tech = "skills.professional_network_skills", "experience.employment_details.current.description"
    tree = group("and",
        group("and", group("or", cond(TITLE, "(.)", ["Backend Engineer", "Platform Engineer"])), group("or", cond(skills, "(.)", ["Java", "Python"]))),
        group("or", cond(tech, "(.)", ["LLM", "RAG"])))
    result = build(tree)
    assert result["ok"]
    inner = result["filters"]["conditions"][0]
    assert inner["op"] == "and" and inner["conditions"][0]["op"] == "or" and inner["conditions"][0]["conditions"][0]["op"] == "or"
    deep = group("and", *[group("or", cond(TITLE, "(.)", ["a"]))])
    for _ in range(12):
        deep = group("and", deep, cond(TITLE, "(.)", ["b"]))
    assert build(deep)["ok"]


# --- values are used exactly as entered ------------------------------------------------------------------------------
def test_values_are_never_interpreted_expanded_or_normalised() -> None:
    values = ["Backend Engineer", "backend  engineer", "Sofware Enginer", " Platform Engineer "]      # typo, double space, padding
    result = build(group("and", cond(TITLE, "(.)", values)))
    sent = [c["value"] for c in result["filters"]["conditions"][0]["conditions"]]
    assert sent == values                                                        # untouched: no synonyms, no correction, no trim
    assert any("whitespace" in w["message"] for w in result["warnings"])         # flagged, not fixed
    assert "Application Developer" not in json.dumps(result["filters"])         # titles.json expansion is not applied


def test_only_strictly_required_type_coercion_happens() -> None:
    result = build(group("and", cond("years_of_experience_raw", "=>", ["8"]), cond("recently_changed_jobs", "=", ["true"])))
    assert result["filters"]["conditions"] == [leaf("years_of_experience_raw", "=>", 8), leaf("recently_changed_jobs", "=", True)]
    assert not build(group("and", cond("years_of_experience_raw", "=>", ["eight"])))["ok"]


def test_in_operator_sends_one_list_and_geo_distance_has_the_provider_shape() -> None:
    result = build(group("and", cond("basic_profile.location.country", "in", ["Canada", "United States"]),
                         cond("basic_profile.location", "geo_distance", geo={"location": "Toronto, ON", "distance": "25", "unit": "mi"})))
    assert result["filters"]["conditions"] == [
        leaf("basic_profile.location.country", "in", ["Canada", "United States"]),
        leaf("basic_profile.location", "geo_distance", {"location": "Toronto, ON", "distance": 25, "unit": "mi"})]
    assert not build(group("and", cond("basic_profile.location", "geo_distance", geo={"location": "", "distance": "5"})))["ok"]


def test_boolean_text_inside_a_value_is_flagged_not_rewritten() -> None:
    result = build(group("and", cond(TITLE, "(.)", ['("development" OR "developer")'])))
    assert result["filters"]["conditions"][0]["value"] == '("development" OR "developer")'
    assert any("Boolean" in w["message"] for w in result["warnings"])


# --- validation rules --------------------------------------------------------------------------------------------------
def test_unknown_fields_and_wrong_operators_are_errors_never_silently_fixed() -> None:
    assert not build(group("and", cond("zip_code", "=", ["M5V"])))["ok"]
    assert not build(group("and", cond("work_mode", "=", ["hybrid"])))["ok"]
    bad_op = build(group("and", cond("years_of_experience_raw", ">=", ["5"])))
    assert not bad_op["ok"] and "not a CrustData filter operator" in bad_op["errors"][0]["message"]
    assert not build(group("and", cond("recently_changed_jobs", "(.)", ["x"])))["ok"]
    assert not build(group("or"))["ok"] and not build({})["ok"]                # empty group / empty query


def test_status_shows_up_as_warnings_and_notes() -> None:
    red = build(group("and", cond("years_of_experience", "=", ["More than 10 years"])))
    assert red["ok"] and any("UNAVAILABLE" in w["message"] for w in red["warnings"])
    assert red["filters"]["conditions"][0]["field"] == "years_of_experience"       # not converted to years_of_experience_raw
    yellow = build(group("and", cond("education.schools.school", "(.)", ["Stanford"])))
    assert any("not yet verified" in n["message"] for n in yellow["notes"])
    green = build(group("and", cond(TITLE, "(.)", ["Engineer"])))
    assert not green["warnings"] and not green["notes"]


def test_closed_set_values_outside_the_list_are_warned_and_still_sent_unchanged() -> None:
    result = build(group("and", cond("experience.employment_details.current.seniority_level", "=", ["Founder"])))
    assert any("closed value set" in w["message"] for w in result["warnings"])
    assert result["filters"]["conditions"][0]["value"] == "Founder"
    assert not build(group("and", cond("experience.employment_details.current.seniority_level", "=", ["director"])))["warnings"]   # = ignores case


def test_all_of_rules() -> None:
    T2, C2 = "experience.employment_details.title", "experience.employment_details.company_id"
    ok = build(group("all_of", group("and", cond(T2, "(.)", ["Engineer"]), cond(C2, "=", ["629097"])), group("and", cond(T2, "(.)", ["Manager"]), cond(C2, "=", ["632500"]))))
    assert ok["ok"] and ok["filters"]["op"] == "all_of"
    assert not build(group("all_of", cond("basic_profile.name", "(.)", ["x"])))["ok"]                                         # scalar field
    assert not build(group("all_of", cond(T2, "(.)", ["a"]), cond("education.schools.school", "(.)", ["b"])))["ok"]           # mixed paths
    assert not build(group("all_of", cond(T2, "(!)", ["Intern"])))["ok"]                                                      # negation
    assert not build(group("all_of", group("all_of", cond(T2, "(.)", ["a"]))))["ok"]                                          # nested all_of
    assert not build(group("all_of", cond("experience.employment_details.company_id", "has_all", ["1", "2"])))["ok"]          # has_all inside all_of
    assert build(group("and", cond(C2, "has_all", ["629097", "632500"])))["filters"]["conditions"][0] == leaf(C2, "has_all", [629097, 632500])
    combined = build(group("and", cond(T2, "(.)", ["Engineer", "Manager"], combine="all_of")))
    assert combined["ok"] and combined["filters"]["conditions"][0]["op"] == "all_of"
    assert not build(group("and", cond("basic_profile.name", "(.)", ["a", "b"], combine="all_of")))["ok"]
    same_entry = build(group("and", cond(T2, "(.)", ["a"]), cond(C2, "=", ["1"])))
    assert any("SAME entry" in n["message"] for n in same_entry["notes"])


# --- running -----------------------------------------------------------------------------------------------------------
def _fake_client(items, captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.read().decode("utf-8")))
        return httpx.Response(200, json={"profiles": items, "total_count": 42, "next_cursor": "c"}, headers={"x-credits-used": "0.3"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _profile(pid, name):
    return {"crustdata_person_id": pid, "basic_profile": {"name": name}, "experience": {"employment_details": {"current": [{"title": "Engineer", "name": "Acme"}]}}}


@pytest.fixture()
def playground(monkeypatch, tmp_path):
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key")
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "runs")
    captured: list = []
    app = create_app(token="tok", client=_fake_client([_profile(9, "Zed"), _profile(1, "Ada")], captured))
    return TestClient(app), captured, {"X-Playground-Token": "tok"}


def test_run_sends_exactly_the_built_filters_and_nothing_else_and_keeps_provider_order(playground) -> None:
    client, captured, headers = playground
    tree = group("and", group("or", cond(TITLE, "(.)", ["Backend Engineer", "Platform Engineer"])))
    built = client.post("/api/build", json={"tree": tree}, headers=headers).json()
    response = client.post("/api/run", json={"tree": tree, "limit": 5}, headers=headers)
    assert response.status_code == 200
    body = captured[0]
    assert body["filters"] == built["filters"]
    assert set(body) == {"filters", "limit", "fields"} and "search" not in body and body["limit"] == 5
    data = response.json()
    assert [r["crustdata_person_id"] for r in data["rows"]] == [9, 1] and [r["position"] for r in data["rows"]] == [1, 2]
    assert data["total_count_provider_reported"] == 42 and data["credits_used_header"] == "0.3"
    assert Path(data["saved_to"]).exists()


def test_a_query_with_errors_is_never_sent(playground) -> None:
    client, captured, headers = playground
    response = client.post("/api/run", json={"tree": group("and", cond("zip_code", "=", ["M5V"]))}, headers=headers)
    assert response.status_code == 422 and captured == []


def test_unavailable_fields_need_explicit_confirmation(playground) -> None:
    client, captured, headers = playground
    tree = group("and", cond("years_of_experience", "=", ["More than 10 years"]))
    assert client.post("/api/run", json={"tree": tree}, headers=headers).status_code == 409 and captured == []
    assert client.post("/api/run", json={"tree": tree, "confirm_unavailable": True}, headers=headers).status_code == 200


def test_limit_and_response_fields_are_bounded(playground) -> None:
    client, captured, headers = playground
    tree = group("and", cond(TITLE, "(.)", ["x"]))
    assert client.post("/api/run", json={"tree": tree, "limit": 500}, headers=headers).status_code == 400
    assert client.post("/api/run", json={"tree": tree, "limit": 5, "fields": ["skills"]}, headers=headers).status_code == 400
    assert captured == []


def test_the_local_server_requires_its_token_and_serves_the_catalog(playground) -> None:
    client, _, headers = playground
    assert client.get("/api/catalog").status_code == 403
    assert client.post("/api/build", json={"tree": {}}, headers={"X-Playground-Token": "wrong"}).status_code == 403
    catalog = client.get("/api/catalog", headers=headers).json()
    assert len(catalog["fields"]) == len(CATALOG) and catalog["max_limit"] == 50
    assert 'content="tok"' in client.get("/").text and 'content="tok"' in client.get("/advanced").text


def test_playground_does_not_touch_production_search_storage(playground) -> None:
    client, _, headers = playground
    store = Path(SearchStore().storage_dir)
    before = set(store.glob("*.json")) if store.exists() else set()
    client.post("/api/run", json={"tree": group("and", cond(TITLE, "(.)", ["x"])), "limit": 1}, headers=headers)
    assert (set(store.glob("*.json")) if store.exists() else set()) == before


def test_every_run_is_saved_and_can_be_listed_reloaded_and_restored(playground) -> None:
    client, _, headers = playground
    tree = group("and", cond(TITLE, "(.)", ["Backend Engineer"]))
    run = client.post("/api/run", json={"tree": tree, "limit": 2}, headers=headers).json()
    listing = client.get("/api/runs", headers=headers).json()
    assert listing[0]["run_id"] == run["run_id"] and listing[0]["retrieved_count"] == 2 and "Backend Engineer" in listing[0]["boolean_text"]
    saved = client.get(f"/api/runs/{run['run_id']}", headers=headers).json()
    assert saved["context"]["tree"] == tree                                   # the query can be restored
    assert [r["crustdata_person_id"] for r in saved["rows"]] == [9, 1] and len(saved["raw_items"]) == 2
    assert client.get("/api/runs/../../etc/passwd", headers=headers).status_code == 404
    assert client.get("/api/runs/run_x", headers=headers).status_code == 404
    assert client.get("/api/runs").status_code == 403


# --- recruiter-level (simple) layer -------------------------------------------------------------------------------------
from backend.experiments.structured_playground import simple  # noqa: E402


def f(filter_id, values=None, mode="include", **extra):
    return {"type": "filter", "filter": filter_id, "mode": mode, "values": values or [], **extra}


def test_every_simple_filter_maps_to_a_real_catalog_field_and_offered_operators() -> None:
    for spec in simple.FILTERS:
        assert spec["field"] in BY_NAME, spec["id"]
    assert len({s["id"] for s in simple.FILTERS}) == len(simple.FILTERS)
    status = {s["id"]: s["status"] for s in simple.filters_payload()}
    assert status["job_title"] == "verified" and status["skills"] == "unavailable" and status["school"] == "documented_unverified"


def test_recruiter_search_becomes_the_same_tree_the_advanced_builder_validates() -> None:
    state = {"combine": "and", "items": [
        f("job_title", ["Backend Engineer", "Platform Engineer"]),
        f("city", ["Toronto"]),
        f("job_title", ["Intern", "Trainee"], mode="exclude"),
        f("years", min="5", max="12"),
    ]}
    tree, problems = simple.to_tree(state)
    assert problems == [] and tree["op"] == "and"
    built = build(tree)["filters"]["conditions"]
    assert built[0] == {"op": "or", "conditions": [leaf(TITLE, "(.)", "Backend Engineer"), leaf(TITLE, "(.)", "Platform Engineer")]}
    assert built[1] == leaf("basic_profile.location.city", "in", ["Toronto"])
    assert built[2] == {"op": "and", "conditions": [leaf(TITLE, "(!)", "Intern"), leaf(TITLE, "(!)", "Trainee")]}   # NOT a AND NOT b
    assert built[3] == {"op": "and", "conditions": [leaf("years_of_experience_raw", "=>", 5), leaf("years_of_experience_raw", "=<", 12)]}


def test_plain_choices_map_to_operators_and_values_stay_verbatim() -> None:
    tree, _ = simple.to_tree({"combine": "and", "items": [f("job_title", ["Sofware  Enginer"], phrase=True)]})
    assert build(tree)["filters"]["conditions"][0] == leaf(TITLE, "[.]", "Sofware  Enginer")
    tree, _ = simple.to_tree({"combine": "and", "items": [f("job_title", ["A", "B"], match="all")]})
    assert build(tree)["filters"]["conditions"][0]["op"] == "and"
    tree, _ = simple.to_tree({"combine": "and", "items": [f("company", ["Shopify"], mode="exclude"), f("seniority", ["Senior", "Director"])]})
    assert build(tree)["filters"]["conditions"] == [leaf("experience.employment_details.current.company_name", "not_in", ["Shopify"]),
                                                      leaf("experience.employment_details.current.seniority_level", "in", ["Senior", "Director"])]
    tree, _ = simple.to_tree({"combine": "and", "items": [f("distance", place="Toronto, ON", distance="25", unit="mi"), f("distance", mode="exclude", place="Waterloo", distance="10", unit="km")]})
    conditions = build(tree)["filters"]["conditions"]
    assert conditions[0] == leaf("basic_profile.location", "geo_distance", {"location": "Toronto, ON", "distance": 25, "unit": "mi"})
    assert conditions[1]["type"] == "geo_exclude"


def test_groups_give_recruiters_brackets_with_their_own_and_or() -> None:
    state = {"combine": "and", "items": [
        {"type": "group", "combine": "or", "items": [f("city", ["Toronto"]), f("city", ["Waterloo"])]},
        f("job_title", ["Backend Engineer"])]}
    tree, problems = simple.to_tree(state)
    assert problems == [] and tree["children"][0]["op"] == "or"
    text = simple.to_text(state)
    assert "OR" in text and "AND" in text and "(" in text and 'City: "Toronto"' in text


def test_incomplete_filters_get_recruiter_language_problems_not_technical_errors() -> None:
    _, problems = simple.to_tree({"combine": "and", "items": [f("job_title"), f("years"), f("distance")]})
    assert any("Current job title: add at least one value" in p for p in problems)
    assert any("Years of experience" in p for p in problems) and any("place and a distance" in p for p in problems)
    assert simple.to_tree({"items": []})[0] is None
    _, group_problems = simple.to_tree({"items": [{"type": "group", "combine": "or", "items": []}]})
    assert any("group is empty" in p for p in group_problems)


def test_the_search_reads_back_in_recruiter_notation() -> None:
    text = simple.to_text({"combine": "and", "items": [f("job_title", ["Backend Engineer", "Platform Engineer"]), f("job_title", ["Intern"], mode="exclude"), f("years", min="5")]})
    assert 'Current job title: ("Backend Engineer" OR "Platform Engineer")' in text
    assert 'Current job title: NOT "Intern"' in text and "Years of experience: at least 5" in text and "\nAND\n" in text


def test_simple_endpoints_build_run_and_save_the_recruiter_state(playground) -> None:
    client, captured, headers = playground
    state = {"combine": "and", "items": [f("job_title", ["Backend Engineer"]), f("skills", ["Python"])]}
    filters = client.get("/api/simple/filters", headers=headers).json()
    assert len(filters["filters"]) == len(simple.FILTERS)
    built = client.post("/api/simple/build", json={"state": state}, headers=headers).json()
    assert built["ok"] and any("Skills" in w for w in built["warnings"]) and 'Current job title: "Backend Engineer"' in built["text"]
    incomplete = client.post("/api/simple/build", json={"state": {"items": [f("city")]}}, headers=headers).json()
    assert not incomplete["ok"] and "City: add at least one value" in incomplete["problems"][0]
    assert client.post("/api/simple/run", json={"state": state}, headers=headers).status_code == 409 and captured == []   # skills is unavailable
    ok_state = {"combine": "and", "items": [f("job_title", ["Backend Engineer"]), f("city", ["Toronto"])]}
    run = client.post("/api/simple/run", json={"state": ok_state, "limit": 3}, headers=headers)
    assert run.status_code == 200 and captured[0]["limit"] == 3 and "search" not in captured[0]
    saved = client.get(f"/api/runs/{run.json()['run_id']}", headers=headers).json()
    assert saved["context"]["ui_state"] == ok_state                                # can be reused from the recruiter page
    assert client.post("/api/simple/run", json={"state": {"items": []}}, headers=headers).status_code == 422
