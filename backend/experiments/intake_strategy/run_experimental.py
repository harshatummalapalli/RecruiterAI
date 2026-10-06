"""Experimental arm: Role 1 through the extended representation, N times (EXPERIMENT ONLY).

    python -m backend.experiments.intake_strategy.run_experimental --runs 5

Same JD, same brief, same model and reasoning effort as the baseline (imported from production, not re-declared). Only the
prompt (prompt_v2.txt) and the parse target (ExperimentalHiringIntent) differ. The compiler is NOT called: this arm tests
the representation, and compiler behaviour is deliberately unchanged and out of scope. Never imports a provider, Harvest,
the search pipeline or the judge.

Transport: the experimental reply is much larger than the baseline's (per-atom provenance), and a non-streaming request
that runs past ~90 s is cut off upstream ("InternalServerError: upstream request failed", observed 5/5 on the first
attempt, each at ~92 s; the baseline's failed run 5 died at the same point). The reply is therefore streamed and
reassembled into the SAME final response object. Model, reasoning effort, prompt text and parse path are unchanged.

A parse/validation failure is recorded as a result (a structural failure rate is a stability signal). Only transient
transport/server errors (HTTP 5xx, connection, timeout) are retried, at most twice, and each retry is recorded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.experiments.intake_strategy import gold_experimental as gold
from backend.experiments.intake_strategy.experimental_extractor import extract_experimental_intent
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent, effective_view
from backend.experiments.intake_strategy.run_baseline import DEFAULT_OUT, RecordingClient, load_inputs
from backend.services.structured_intent_extractor import _INTAKE_MODEL, _INTAKE_REASONING_EFFORT

MAX_TRANSIENT_RETRIES = 2


class StreamingRecordingClient(RecordingClient):
    """RecordingClient that streams, then hands back the final response object exactly as a non-streaming call would."""

    def create(self, **kwargs: Any) -> Any:
        final = None
        for event in self._inner.responses.create(stream=True, **kwargs):
            if getattr(event, "type", None) == "response.completed":
                final = event.response
            elif getattr(event, "type", None) in ("response.failed", "response.incomplete"):
                raise RuntimeError(f"model response {event.type}: {getattr(getattr(event, 'response', None), 'error', None)}")
        if final is None:
            raise RuntimeError("stream ended without response.completed")
        usage = getattr(final, "usage", None)
        self.calls.append(
            {
                "model": kwargs.get("model"),
                "reasoning": kwargs.get("reasoning"),
                "prompt": kwargs.get("input"),
                "raw_text": getattr(final, "output_text", None),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                "streamed": True,
            }
        )
        return final


def _is_transient(exc: Exception) -> bool:
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    return name in ("APIConnectionError", "APITimeoutError", "InternalServerError") or (isinstance(status, int) and status >= 500)


def run_once(index: int, client_factory: Callable[[], Any], jd: str, brief: str) -> Dict[str, Any]:
    client = StreamingRecordingClient(client_factory())
    started = time.perf_counter()
    record: Dict[str, Any] = {"run": index, "error": None, "transient_retries": []}
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            intent = extract_experimental_intent(jd, brief, client)
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


# ---------------------------------------------------------------------------- semantic stability


def components(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Semantic components compared across runs: meaning, never the raw JSON."""
    if record.get("intent") is None:
        return None
    intent = ExperimentalHiringIntent.model_validate(record["intent"])
    a, b = gold.find_paths(intent)
    va = effective_view(intent, a.id) if a else None
    vb = effective_view(intent, b.id) if b else None

    def skill(view: Optional[Dict[str, Any]], name: str) -> Optional[str]:
        if not view:
            return None
        hit = [s for s in view["skills"] if name in s.name.lower()]
        return f"{hit[0].strength}/{hit[0].proficiency}" if hit else "absent"

    by_id = {g["id"]: g for g in record["gold"]["critical"]}
    rec_ok = by_id["reconciliation_visible"]["evidence"]
    prov = record["gold"]["validation"]["status_counts"]
    atoms = sum(prov.values())
    return {
        "path_strategies": tuple(sorted(p.strategy for p in intent.sourcing_paths)),
        "geography_A": tuple(gold._heads(va["location"])) if va else None,
        "geography_B": tuple(gold._heads(vb["location"])) if vb else None,
        "power_query_A": skill(va, "power query"),
        "power_query_B": skill(vb, "power query"),
        "sql_B": skill(vb, "sql"),
        "python_B": skill(vb, "python"),
        "experience_B": (vb["experience"].minimum_years, vb["experience"].strength) if vb and vb["experience"] else None,
        "seniority_B": (vb["seniority"].value.lower(), vb["seniority"].strength, tuple(sorted(vb["seniority"].leadership))) if vb and vb["seniority"] else None,
        "seniority_A": (va["seniority"].value.lower(), va["seniority"].strength, tuple(sorted(va["seniority"].leadership))) if va and va["seniority"] else None,
        "domain_A": tuple(sorted((d.strength) for d in va["domain"])) if va else None,
        "domain_B_required": any(d.strength == "required" for d in vb["domain"]) if vb else None,
        "semantic_negative": bool(by_id["hard_negative_secops_preserved"]["status"] == gold.PASS),
        "company_exclusions": len([x for x in intent.exclusions if "company" in x.kind]),
        "reconciliations_expected_found": rec_ok.split(";")[0][:120],
        "basis_coverage": f"{atoms - prov.get('missing', 0)}/{atoms}",
        "unsupported_or_misattributed": prov.get("unsupported", 0) + prov.get("misattributed", 0),
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
    diag: Counter = Counter()
    for r in ok:
        diag.update(d["code"] for d in r["gold"]["validation"]["diagnostics"])
    out["diagnostic_codes_across_runs"] = dict(diag)
    return out


def write_outputs(out_dir: Path, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        (out_dir / f"experimental_run{r['run']}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {
        "arm": "experimental",
        "config": {"model": _INTAKE_MODEL, "reasoning_effort": _INTAKE_REASONING_EFFORT, "prompt": "prompt_v2.txt"},
        "tokens": {
            "input": sum(c["input_tokens"] for r in records for c in r["model_calls"]),
            "output": sum(c["output_tokens"] for r in records for c in r["model_calls"]),
        },
        "stability": stability(records),
    }
    (out_dir / "experimental_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT / "experimental")
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
