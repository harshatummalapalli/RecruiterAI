"""Baseline harness: run the CURRENT, UNCHANGED intake representation on Role 1, N times (EXPERIMENT ONLY).

    python -m backend.experiments.intake_strategy.run_baseline --runs 5

What it calls, unchanged: extract_structured_intent (the sanctioned model + reasoning effort constants live in
structured_intent_extractor), then compile_intent and build_audit_record. Nothing here imports a provider, Harvest, the
search pipeline or the judge, and it never writes outside output/experiments/. The OpenAI client is wrapped only to
record the raw model text and token usage; the wrapper returns the response untouched.

Per run it captures: the raw model text, the parsed StructuredHiringIntent, the compiled plan + audit record, the gold
assertions, the compiler checks, the JD-retention report and the provenance report. A parse/validation failure is
captured as a result, not hidden: structural failure rate is itself a stability signal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.experiments.intake_strategy import gold_assertions as gold
from backend.experiments.intake_strategy.provenance import provenance_report
from backend.services.compiler_audit import build_audit_record
from backend.services.search_compiler import compile_intent
from backend.services.structured_intent_extractor import (
    _INTAKE_MODEL,
    _INTAKE_REASONING_EFFORT,
    extract_structured_intent,
)

INPUT_DIR = Path(__file__).parent / "inputs"
DEFAULT_OUT = Path("output/experiments/intake_strategy")


def load_inputs() -> Dict[str, str]:
    return {
        "jd": (INPUT_DIR / "role1_jd.txt").read_text(encoding="utf-8"),
        "brief": (INPUT_DIR / "role1_recruiter_brief.txt").read_text(encoding="utf-8"),
    }


class RecordingClient:
    """Wraps an OpenAI-style client. Records every request/response; returns the response unchanged."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: List[Dict[str, Any]] = []
        self.responses = self  # the extractor calls client.responses.create(...)

    def create(self, **kwargs: Any) -> Any:
        response = self._inner.responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        self.calls.append(
            {
                "model": kwargs.get("model"),
                "reasoning": kwargs.get("reasoning"),
                "prompt": kwargs.get("input"),
                "raw_text": getattr(response, "output_text", None),
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        return response


def run_once(index: int, client_factory: Callable[[], Any], jd: str, brief: str) -> Dict[str, Any]:
    client = RecordingClient(client_factory())
    started = time.perf_counter()
    record: Dict[str, Any] = {"run": index, "error": None}
    try:
        intent = extract_structured_intent(jd, recruiter_brief=brief, client=client)
        plan = compile_intent(intent)
        record.update(
            {
                "intent": intent.model_dump(),
                "compiled": {
                    "filter_tree": plan.filter_tree,
                    "retrieval_title_family": plan.retrieval_title_family,
                    "warnings": plan.warnings,
                    "audit": [vars(c) for c in plan.audit],
                },
                "audit_record": build_audit_record(intent, plan, search_id=f"baseline-run-{index}"),
                "gold": gold.evaluate(intent, plan),
                "provenance": provenance_report(intent, jd, brief),
            }
        )
    except Exception as exc:  # noqa: BLE001 - a failed run is data
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["model_calls"] = client.calls
    record["elapsed_s"] = round(time.perf_counter() - started, 2)
    return record


# ---------------------------------------------------------------------------- semantic stability


def _tool_strength(intent: Dict[str, Any], tool: str) -> Optional[str]:
    strengths = sorted({s["strength"] for s in intent.get("skills", []) if tool in s["name"].lower()})
    return "/".join(strengths) or None


def components(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Semantic components compared across runs. Deliberately not the raw JSON: wording may vary, meaning may not."""
    intent = record.get("intent")
    if intent is None:
        return None
    gold_by_id = {g["id"]: g for g in record["gold"]["critical"]}
    location = intent.get("location") or {}
    return {
        "structure": tuple(sorted(k for k, v in intent.items() if v)),
        "archetype": intent["role_archetype"]["value"],
        "paths": 0,  # the current schema cannot carry paths
        "seniority": (intent.get("seniority") or {}).get("value", "").lower() or None,
        "must_preferred": (_tool_strength(intent, "sql"), _tool_strength(intent, "python"), _tool_strength(intent, "power query")),
        "experience": ((intent.get("experience") or {}).get("minimum_years"), (intent.get("experience") or {}).get("strength")),
        "negatives": tuple(sorted(x["value"].lower() for x in intent.get("exclusions", []))),
        "geography": (tuple(sorted(e.lower() for e in location.get("entries", []))), bool(location.get("radius"))),
        "domain_distinction": (gold_by_id["cyber_review_not_secops"]["status"], gold_by_id["cyber_review_not_secops"]["failure_class"]),
        "provenance_inferred_required": len(record["provenance"]["inferred_but_required"]),
    }


def stability(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in records if r.get("intent") is not None]
    out: Dict[str, Any] = {"runs": len(records), "parsed": len(ok), "errors": [r["error"] for r in records if r["error"]]}
    if not ok:
        return out
    comps = [components(r) for r in ok]
    shares: Dict[str, Any] = {}
    for key in comps[0]:
        counter = Counter(repr(c[key]) for c in comps)
        value, count = counter.most_common(1)[0]
        shares[key] = {"modal_value": value, "agreement": f"{count}/{len(comps)}", "distinct": len(counter)}
    out["components"] = shares
    statuses: Dict[str, Dict[str, int]] = {}
    for r in ok:
        for g in r["gold"]["critical"] + r["gold"]["compiler"]:
            statuses.setdefault(g["id"], Counter())[g["status"]] += 1  # type: ignore[arg-type]
    out["assertion_statuses"] = {k: dict(v) for k, v in statuses.items()}
    return out


def write_outputs(out_dir: Path, arm: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        (out_dir / f"{arm}_run{r['run']}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {
        "arm": arm,
        "config": {"model": _INTAKE_MODEL, "reasoning_effort": _INTAKE_REASONING_EFFORT},
        "tokens": {
            "input": sum(c["input_tokens"] for r in records for c in r["model_calls"]),
            "output": sum(c["output_tokens"] for r in records for c in r["model_calls"]),
        },
        "stability": stability(records),
    }
    (out_dir / f"{arm}_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT / "baseline")
    args = parser.parse_args(argv)

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; refusing to run. No network call was made.", file=sys.stderr)
        return 2
    from openai import OpenAI  # imported late so the evaluator/tests never need the SDK

    inputs = load_inputs()
    factory = lambda: OpenAI(api_key=os.environ["OPENAI_API_KEY"])  # noqa: E731
    records = [run_once(i + 1, factory, inputs["jd"], inputs["brief"]) for i in range(args.runs)]
    summary = write_outputs(args.out, "baseline", records)
    print(json.dumps(summary["stability"].get("assertion_statuses", {}), indent=2))
    print(f"wrote {len(records)} runs to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
