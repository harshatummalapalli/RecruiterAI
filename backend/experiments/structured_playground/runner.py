"""Optionally run EXACTLY the query the builder produced against CrustData /person/search.

- One request, no retries (a retry would spend credits twice), no `search` clause, no ranking, no SearchStore.
- The request body is `filters` + `limit` + `fields`; nothing else is added.
- Each run is written to output/experiments/structured_playground/runs/ (gitignored; contains candidate data)."""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_crustdata_api_key
from backend.providers.crustdata import API_VERSION, DEFAULT_FIELDS

ENDPOINT = "https://api.crustdata.com/person/search"
MAX_LIMIT = 50
CREDITS_PER_RESULT = 0.03   # CrustData's published ~0.03 credits/result for person_search
PROJECTABLE_FIELDS = ["crustdata_person_id", "basic_profile", "contact", "social_handles", "experience", "education", "metadata", "fit"]
RUNS_DIR = Path(__file__).resolve().parents[3] / "output" / "experiments" / "structured_playground" / "runs"


class RunError(Exception):
    pass


def build_request(filters: Dict[str, Any], limit: int, fields: Optional[List[str]] = None) -> Dict[str, Any]:
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise RunError(f"limit must be an integer from 1 to {MAX_LIMIT}.")
    chosen = list(fields) if fields else list(DEFAULT_FIELDS)
    unknown = [f for f in chosen if f not in PROJECTABLE_FIELDS]
    if unknown:
        raise RunError(f"Unknown response field group(s): {', '.join(unknown)}. Allowed: {', '.join(PROJECTABLE_FIELDS)}.")
    return {"filters": filters, "limit": limit, "fields": chosen}


def estimate_credits(limit: int) -> float:
    return round(limit * CREDITS_PER_RESULT, 2)


def _rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for position, item in enumerate(items, start=1):
        basic = item.get("basic_profile") or {}
        current = ((item.get("experience") or {}).get("employment_details") or {}).get("current") or []
        first = current[0] if current else {}
        location = basic.get("location") or {}
        rows.append(
            {
                "position": position,
                "crustdata_person_id": item.get("crustdata_person_id"),
                "name": basic.get("name"),
                "headline": basic.get("headline"),
                "current_title": first.get("title") or basic.get("current_title"),
                "current_company": first.get("name"),
                "location": ", ".join(str(x) for x in (location.get("city"), location.get("state"), location.get("country")) if x),
                "profile_url": (((item.get("social_handles") or {}).get("professional_network_identifier")) or {}).get("profile_url"),
                "fit": item.get("fit"),
            }
        )
    return rows


def run(filters: Dict[str, Any], limit: int, fields: Optional[List[str]] = None, client: Optional[httpx.Client] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = get_crustdata_api_key()
    if not key:
        raise RunError("CRUSTDATA_API_KEY is not configured.")
    body = build_request(filters, limit, fields)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "x-api-version": API_VERSION}
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    started = time.perf_counter()
    try:
        response = client.post(ENDPOINT, json=body, headers=headers)
    except httpx.RequestError as exc:
        raise RunError(f"Request failed: {exc}") from exc
    finally:
        if owns:
            client.close()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text[:2000]}
    result: Dict[str, Any] = {
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "context": context or {},        # the builder tree + Boolean text that produced this request
        "request": body,
        "http_status": response.status_code,
        "elapsed_ms": elapsed_ms,
        "credits_used_header": response.headers.get("x-credits-used"),
    }
    if response.status_code != 200:
        result["error_body"] = payload
        _save(result)
        return result
    items = payload.get("profiles") or []
    envelope = {k: v for k, v in payload.items() if k != "profiles"}
    result.update(
        {
            "response_envelope": envelope,
            "total_count_provider_reported": envelope.get("total_count"),
            "retrieved_count": len(items),
            "has_next_cursor": bool(envelope.get("next_cursor")),
            "rows": _rows(items),          # provider order, 1..N
            "raw_items": items,
        }
    )
    _save(result)
    return result


def _save(result: Dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}"
    path = RUNS_DIR / f"{run_id}.json"
    result["run_id"] = run_id
    result["saved_to"] = str(path)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


_RUN_ID = re.compile(r"^run_\d{8}_\d{6}_\d{3}$")


def list_runs() -> List[Dict[str, Any]]:
    """Newest first: a one-line summary of every saved run."""
    if not RUNS_DIR.exists():
        return []
    out = []
    for path in sorted(RUNS_DIR.glob("run_*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({
            "run_id": path.stem, "saved_at": data.get("saved_at"), "http_status": data.get("http_status"),
            "retrieved_count": data.get("retrieved_count"), "total_count": data.get("total_count_provider_reported"),
            "limit": (data.get("request") or {}).get("limit"),
            "boolean_text": ((data.get("context") or {}).get("boolean_text") or "")[:300],
        })
    return out


def load_run(run_id: str) -> Dict[str, Any]:
    if not _RUN_ID.match(run_id):
        raise RunError("Invalid run id.")
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        raise RunError("No such saved run.")
    return json.loads(path.read_text(encoding="utf-8"))
