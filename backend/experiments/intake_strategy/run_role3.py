"""Role 3 runner: JD-ONLY, the FROZEN representation + prompt_v4 + frozen validators, five times (EXPERIMENT ONLY).

    python -m backend.experiments.intake_strategy.run_role3 --runs 5

There is NO recruiter brief for this role and none is passed (the prompt receives "(none provided)"). Nothing about the prompt, schema or
validators is changed for this role: the prompt file's hash is recorded in the summary and pinned by a test. Same model and reasoning
effort as every earlier arm (imported from production); the reply is streamed (see run_experimental). The compiler is NOT called here.
A parse/validation failure is a result. Only transient transport errors are retried (at most twice), and every retry is recorded
separately in `transient_retries`.
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

from backend.experiments.intake_strategy import gold_role3 as gold
from backend.experiments.intake_strategy.experimental_extractor import PROMPTS, extract_experimental_intent
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.run_baseline import DEFAULT_OUT
from backend.experiments.intake_strategy.run_experimental import MAX_TRANSIENT_RETRIES, StreamingRecordingClient, _is_transient
from backend.services.structured_intent_extractor import _INTAKE_MODEL, _INTAKE_REASONING_EFFORT

INPUT_DIR = Path(__file__).parent / "inputs"
PROMPT = "v4"  # frozen for this phase
NO_BRIEF = ""   # Role 3 has none


def load_inputs() -> Dict[str, str]:
    return {"jd": (INPUT_DIR / "role3_jd.txt").read_text(encoding="utf-8")}


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPTS[PROMPT].read_bytes()).hexdigest()


def run_once(index: int, client_factory: Callable[[], Any], jd: str) -> Dict[str, Any]:
    client = StreamingRecordingClient(client_factory())
    started = time.perf_counter()
    record: Dict[str, Any] = {"run": index, "error": None, "transient_retries": []}
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            intent = extract_experimental_intent(jd, NO_BRIEF, client, PROMPT)
            record.update({"intent": intent.model_dump(), "gold": gold.evaluate(intent, jd)})
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
    sen, loc, exp, edu = it.seniority, it.location, it.experience, it.education
    prof = {k: sorted({s.proficiency or "none" for s in it.skills if rx in s.name.lower()}) for k, rx in (("excel", "excel"), ("power_bi", "power bi"))}
    others = sorted(s.name for s in it.skills if s.proficiency and not any(k in s.name.lower() for k in ("excel", "power bi")))
    by_id = {g["id"]: g for g in record["gold"]["critical"]}
    rel = Counter(s.relationship for s in it.skills) + Counter(g.relationship for g in it.skill_any_of)
    return {
        "paths": len(it.sourcing_paths), "reconciliations": len(it.reconciliations),
        "exclusions": len(it.exclusions), "semantic_exclusions": len(it.semantic_exclusions),
        "role_family": tuple(sorted(f.lower() for f in it.role_family)),
        "seniority": (sen.value.lower(), sen.strength, tuple(sen.leadership), tuple(sen.alternatives)) if sen else None,
        "experience": (exp.minimum_years, exp.maximum_years, exp.strength) if exp else None,
        "education": (tuple(sorted(d.lower() for d in edu.degrees)), edu.strength) if edu else None,
        "location": (tuple(sorted(e.split(",")[0].lower() for e in loc.entries)), tuple(loc.countries), loc.remote, loc.work_mode, bool(loc.radius)) if loc else None,
        "proficiency_excel_powerbi": json.dumps(prof, sort_keys=True), "proficiency_elsewhere": tuple(others),
        "companies": tuple(sorted((c.name.lower(), c.strength, c.relationship) for c in it.companies)),
        "company_scale": it.company_scale is not None,
        "relationships": json.dumps(dict(sorted(rel.items()))),
        "domain": tuple(sorted((d.strength) for d in it.domain)),
        "evidence_signal_strengths": json.dumps(dict(sorted(Counter(e.strength for e in it.evidence_signals).items()))),
        "skills": len(it.skills), "evidence_signals": len(it.evidence_signals),
        "validator_errors": tuple(sorted(record["gold"]["validation"]["errors"])),
        "non_pass": tuple(sorted(k for k, g in by_id.items() if g["status"] != "PASS")),
    }


def stability(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in records if r.get("intent") is not None]
    out: Dict[str, Any] = {"runs": len(records), "parsed": len(ok), "errors": [r["error"] for r in records if r["error"]],
                           "transient_retries": {r["run"]: r["transient_retries"] for r in records if r["transient_retries"]}}
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
        (out_dir / f"role3_run{r['run']}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {
        "arm": "role3", "brief": None,
        "config": {"model": _INTAKE_MODEL, "reasoning_effort": _INTAKE_REASONING_EFFORT, "prompt": f"prompt_{PROMPT}.txt", "prompt_sha256": prompt_sha256()},
        "tokens": {"input": sum(c["input_tokens"] for r in records for c in r["model_calls"]), "output": sum(c["output_tokens"] for r in records for c in r["model_calls"])},
        "stability": stability(records),
    }
    (out_dir / "role3_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT / "role3")
    args = parser.parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; refusing to run. No network call was made.", file=sys.stderr)
        return 2
    from openai import OpenAI  # imported late so the evaluator/tests never need the SDK

    jd = load_inputs()["jd"]
    factory = lambda: OpenAI(api_key=os.environ["OPENAI_API_KEY"])  # noqa: E731
    with ThreadPoolExecutor(max_workers=args.runs) as pool:
        records = list(pool.map(lambda i: run_once(i, factory, jd), range(1, args.runs + 1)))
    summary = write_outputs(args.out, records)
    print(json.dumps(summary["stability"].get("assertion_statuses", {}), indent=2))
    print(f"wrote {len(records)} runs to {args.out}; errors={summary['stability']['errors']}; transient_retries={summary['stability']['transient_retries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
