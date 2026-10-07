"""Role 2 cross-role runner: the FROZEN representation, prompt_v3 and validators, five times (EXPERIMENT ONLY).

    python -m backend.experiments.intake_strategy.run_role2 --runs 5

Nothing about the prompt, schema or validators is changed for this role (the prompt file's hash is recorded in the summary and
pinned by a test). Same model and reasoning effort as every earlier arm (imported from production). The reply is streamed for the
reason documented in run_experimental. The compiler is NOT called here; any downstream observation is made offline afterwards
in compare_role2 and recorded, not fixed. A parse/validation failure is recorded as a result, and only transient transport errors
are retried (at most twice).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.experiments.intake_strategy import gold_role2 as gold
from backend.experiments.intake_strategy.experimental_extractor import PROMPTS, extract_experimental_intent
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.run_baseline import DEFAULT_OUT
from backend.experiments.intake_strategy.run_experimental import MAX_TRANSIENT_RETRIES, StreamingRecordingClient, _is_transient
from backend.services.structured_intent_extractor import _INTAKE_MODEL, _INTAKE_REASONING_EFFORT

INPUT_DIR = Path(__file__).parent / "inputs"
PROMPT = "v3"  # frozen: the Role 1 hardening prompt, unchanged


def load_inputs() -> Dict[str, str]:
    return {"jd": (INPUT_DIR / "role2_jd.txt").read_text(encoding="utf-8"), "brief": (INPUT_DIR / "role2_recruiter_brief.txt").read_text(encoding="utf-8")}


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPTS[PROMPT].read_bytes()).hexdigest()


def run_once(index: int, client_factory: Callable[[], Any], jd: str, brief: str) -> Dict[str, Any]:
    client = StreamingRecordingClient(client_factory())
    started = time.perf_counter()
    record: Dict[str, Any] = {"run": index, "error": None, "transient_retries": []}
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            intent = extract_experimental_intent(jd, brief, client, PROMPT)
            record.update({"intent": intent.model_dump(), "gold": gold.evaluate(intent, jd, brief)})
            record["error"] = None
            break
        except Exception as exc:  # noqa: BLE001 - a failed run is data
            record["error"] = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_TRANSIENT_RETRIES and _is_transient(exc):
                record["transient_retries"].append(record["error"])
                time.sleep(2 ** (attempt + 1))
                continue
            break
    record["model_calls"] = client.calls
    record["elapsed_s"] = round(time.perf_counter() - started, 2)
    return record


def components(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Semantic components compared across runs (meaning, not JSON)."""
    if record.get("intent") is None:
        return None
    it = ExperimentalHiringIntent.model_validate(record["intent"])
    items = gold.present_items(it)
    sen, loc, exp, edu = it.seniority, it.location, it.experience, it.education
    prof = {k: sorted({c["proficiency"] or "none" for c in items[k]}) for k in ("python", "java", "genai", "azure_devops", "jira", "metadata")}
    by_id = {g["id"]: g for g in record["gold"]["critical"]}
    return {
        "paths": len(it.sourcing_paths),
        "exclusions": len(it.exclusions) + len(it.semantic_exclusions),
        "companies": len(it.companies) + (1 if it.company_scale else 0),
        "domain_atoms": len(it.domain),
        "role_family": tuple(sorted(f.lower() for f in it.role_family)),
        "seniority": (sen.value.lower(), sen.strength, tuple(sen.leadership), tuple(sen.alternatives)) if sen else None,
        "experience": (exp.minimum_years, exp.strength) if exp else None,
        "education": (tuple(sorted(d.lower() for d in edu.degrees)), edu.strength) if edu else None,
        "location": (tuple(sorted(e.split(",")[0].lower() for e in loc.entries)), tuple(loc.countries), loc.remote, bool(loc.radius)) if loc else None,
        "proficiency": json.dumps(prof, sort_keys=True),
        "cloud_in_or_group": any(c["kind"] == "any_of" for k in ("azure", "aws") for c in items[k]),
        "ml_in_or_group": any(c["kind"] == "any_of" for k in ("tensorflow", "pytorch", "sklearn") for c in items[k]),
        "facts_present": f"{sum(1 for v in items.values() if v)}/{len(items)}",
        "required_atoms": sum(1 for c in gold.claims(it) if c['strength'] == 'required'),
        "reconciliation_actions": tuple(sorted(r.action for r in it.reconciliations)),
        "validator_errors": tuple(sorted(record["gold"]["validation"]["errors"])),
        "non_pass": tuple(sorted(k for k, g in by_id.items() if g["status"] != "PASS")),
    }


def stability(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in records if r.get("intent") is not None]
    out: Dict[str, Any] = {"runs": len(records), "parsed": len(ok), "errors": [r["error"] for r in records if r["error"]]}
    if not ok:
        return out
    comps = [components(r) for r in ok]
    out["components"] = {}
    for key in comps[0]:
        counter = Counter(repr(c[key]) for c in comps)
        value, count = counter.most_common(1)[0]
        out["components"][key] = {"modal_value": value, "agreement": f"{count}/{len(comps)}", "distinct": len(counter), "values": dict(counter)}
    statuses: Dict[str, Counter] = {}
    for r in ok:
        for g in r["gold"]["critical"]:
            statuses.setdefault(g["id"], Counter())[g["status"]] += 1
    out["assertion_statuses"] = {k: dict(v) for k, v in statuses.items()}
    out["diagnostic_codes_across_runs"] = dict(Counter(d["code"] for r in ok for d in r["gold"]["validation"]["diagnostics"]))
    return out


def write_outputs(out_dir: Path, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        (out_dir / f"role2_run{r['run']}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {
        "arm": "role2", "config": {"model": _INTAKE_MODEL, "reasoning_effort": _INTAKE_REASONING_EFFORT, "prompt": f"prompt_{PROMPT}.txt", "prompt_sha256": prompt_sha256()},
        "tokens": {"input": sum(c["input_tokens"] for r in records for c in r["model_calls"]), "output": sum(c["output_tokens"] for r in records for c in r["model_calls"])},
        "stability": stability(records),
    }
    (out_dir / "role2_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT / "role2")
    args = parser.parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; refusing to run. No network call was made.", file=sys.stderr)
        return 2
    from openai import OpenAI  # imported late so the evaluator/tests never need the SDK

    inputs = load_inputs()
    factory = lambda: OpenAI(api_key=os.environ["OPENAI_API_KEY"])  # noqa: E731
    with ThreadPoolExecutor(max_workers=args.runs) as pool:
        records = list(pool.map(lambda i: run_once(i, factory, inputs["jd"], inputs["brief"]), range(1, args.runs + 1)))
    summary = write_outputs(args.out, records)
    print(json.dumps(summary["stability"].get("assertion_statuses", {}), indent=2))
    print(f"wrote {len(records)} runs to {args.out}; errors={summary['stability']['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
