"""Driver for experiment crustdata-nl-vs-structured-20260924.

    python -m backend.experiments.crustdata_retrieval.run prepare    # intents + payloads, NO CrustData calls
    python -m backend.experiments.crustdata_retrieval.run retrieve   # 10 CrustData calls (5 roles x 2 strategies x 1 page of 50)
    python -m backend.experiments.crustdata_retrieval.run evaluate   # Harvest + requirement judge on a bounded sample
    python -m backend.experiments.crustdata_retrieval.run analyze    # comparison tables (no network)

Experiment code only: it never writes to the production SearchStore and never
changes ranking, admission, Harvest or the search path. All artifacts go to
output/experiments/crustdata_nl_vs_structured/<experiment_id>/ (gitignored)."""

import dataclasses
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from pydantic import TypeAdapter

from backend.models.search_intent import SearchIntent
from backend.providers.crustdata import CrustDataProvider

EXPERIMENT_ID = "crustdata-nl-vs-structured-20260924"
ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "output" / "experiments" / "crustdata_nl_vs_structured" / EXPERIMENT_ID
SCRATCH = Path(os.environ.get("EXPERIMENT_SOURCE_DIR", ""))   # where the earlier real intents/JDs were saved

# (role_key, label, why chosen, source of the confirmed intent)
ROLES = [
    ("backend_platform", "Senior Backend / Platform Engineer (US, 8+ yrs)", "canonical role used in the pass 3/4 and phase 3 validations", "stored:pass4_senior_backend_platform_engineer_raw.json"),
    ("ai_platform", "Senior AI Platform Engineer (Toronto, 7+ yrs)", "Epiq role used in the pass 3/4 and phase 3 validations", "stored:pass4_epiq_senior_ai_platform_engineer_raw.json"),
    ("product_manager", "Senior Product Manager, B2B SaaS (US, 6+ yrs)", "non-engineering role used in the pass 3/4 and phase 3 validations", "stored:pass4_senior_product_manager_raw.json"),
    ("cyber_data_analyst_lead", "Data Analyst Lead - Cyber Incident Review (Hyderabad)", "real production search a7d9fad3: highly specific title and domain", "intake:a7d9fad3"),
    ("ai_engineer_ambiguous", "Senior AI Software Engineer (global, broad JD)", "real production search 39917197: 394-char JD, no location, ambiguous scope", "intake:39917197"),
]


def _path(name: str) -> Path:
    return STORE / name


def _dump(name: str, data: Any) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json.dumps(data, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


def _load(name: str) -> Any:
    return json.loads(_path(name).read_text(encoding="utf-8"))


def _intent_from_dict(d: Dict[str, Any]) -> SearchIntent:
    return TypeAdapter(SearchIntent).validate_python(d)


def _intake_intent(search_id_prefix: str) -> Dict[str, Any]:
    """Run the REAL intake (OpenAI) on the JD of an earlier real search and return the confirmed SearchIntent,
    applying that search's saved location exactly as POST /search does."""
    os.environ.setdefault("SESSION_SECRET_KEY", "experiment"); os.environ.setdefault("GOOGLE_CLIENT_ID", "x"); os.environ.setdefault("ALLOWED_EMAIL_DOMAIN", "example.com")
    from fastapi.testclient import TestClient
    from backend.api import create_app
    from backend.auth import SESSION_COOKIE_NAME, create_session_cookie_value

    record = next(p for p in (SCRATCH / "prod_searches" / "searches").glob(f"{search_id_prefix}*.json"))
    record = json.loads(record.read_text(encoding="utf-8"))
    client = TestClient(create_app())
    client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value())
    start = client.post("/intake/start", json={"raw_input": record["jd_text"]}).json()
    sid = start["session_id"]
    for issue in start["result"]["decision"]["issues"]:
        if issue["decision"] == "ask":
            start = client.post(f"/intake/{sid}/answer", json={"issue_id": issue["id"], "value": issue["options"][0]["value"], "label": issue["options"][0]["label"]}).json()
    confirm = client.post(f"/intake/{sid}/confirm")
    confirm.raise_for_status()
    intent = confirm.json()
    loc = record.get("location_override")
    if loc:  # the recruiter's saved Search Brief location is authoritative, as in POST /search
        intent["location"].update({k: loc.get(k) for k in ("countries", "states", "cities", "zip_codes", "radius_miles", "radius_place", "work_mode")} | {"radius_unit": loc.get("radius_unit") or "mi"})
        intent["location"]["zip_codes"] = intent["location"].get("zip_codes") or []
    return {"intent": intent, "jd_text": record["jd_text"], "source_search": record["search_id"], "intake_session": sid}


def prepare() -> None:
    from backend.experiments.crustdata_retrieval.structured import build_nl_plan, build_structured_plan

    provider = CrustDataProvider()
    manifest: Dict[str, Any] = {"experiment_id": EXPERIMENT_ID, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "roles": []}
    for key, label, why, source in ROLES:
        kind, ref = source.split(":", 1)
        if kind == "stored":
            stored = json.loads((SCRATCH / ref).read_text(encoding="utf-8"))
            intent_dict, jd_text, origin = stored["search_intent"], None, source
        else:
            got = _intake_intent(ref)
            intent_dict, jd_text, origin = got["intent"], got["jd_text"], f"real intake on the JD of search {got['source_search']}"
        intent = _intent_from_dict(intent_dict)
        nl = build_nl_plan(intent, provider)
        structured = build_structured_plan(intent, provider)
        role = {
            "role_key": key, "label": label, "why_chosen": why, "intent_origin": origin,
            "intent": dataclasses.asdict(intent), "jd_text": jd_text,
            "nl": {"natural_language_search_query": nl["query"].natural_language_query, "payload": nl["payload"], "dropped_by_capability_mapper": nl["dropped_by_capability_mapper"]},
            "structured": {"payload": structured.payload, "structured_unrepresented_requirement": structured.unrepresented, "dropped_by_capability_mapper": structured.dropped_by_capability_mapper},
        }
        manifest["roles"].append(role)
        print(f"\n== {label}\n   NL query   : {role['nl']['natural_language_search_query']}\n   NL filters : {json.dumps(nl['payload']['filters'])[:400]}\n   STRUCTURED : {json.dumps(structured.payload['filters'])[:400]}\n   unrepresented: {len(structured.unrepresented)} items")
    manifest["planned_crustdata_calls"] = 2 * len(manifest["roles"])
    manifest["max_candidates_retrieved"] = 50 * manifest["planned_crustdata_calls"]
    _dump("manifest.json", manifest)
    print(f"\nPLANNED: {manifest['planned_crustdata_calls']} CrustData calls, first page only, limit 50 each -> at most {manifest['max_candidates_retrieved']} candidates")


def retrieve() -> None:
    from backend.experiments.crustdata_retrieval.capture import capture_first_page

    manifest = _load("manifest.json")
    provider = CrustDataProvider()
    calls = 0
    for role in manifest["roles"]:
        for strategy in ("nl", "structured"):
            out_name = f"retrieval_{role['role_key']}_{strategy}.json"
            if _path(out_name).exists():
                print("skip (already captured):", out_name)
                continue
            payload = role[strategy]["payload"]
            capture = capture_first_page(provider, strategy, payload, "natural_language" if strategy == "nl" else "structured")
            calls += 1
            _dump(out_name, {
                "experiment_id": EXPERIMENT_ID, "role_key": role["role_key"], "strategy": strategy, "request_payload": payload,
                "response_envelope": capture.response_envelope, "retrieved_count": len(capture.rows),
                "total_count_provider_reported_search_universe": capture.total_count, "next_cursor": capture.next_cursor,
                "elapsed_ms": capture.elapsed_ms, "rows": capture.rows, "raw_items": capture.raw_items,
            })
            print(f"{role['role_key']:26} {strategy:10} retrieved={len(capture.rows):3} universe={capture.total_count} cursor={'yes' if capture.next_cursor else 'no'} envelope_keys={sorted(capture.response_envelope)} {capture.elapsed_ms}ms")
    print("CrustData calls made this run:", calls)


if __name__ == "__main__":
    {"prepare": prepare, "retrieve": retrieve}[sys.argv[1]]()
