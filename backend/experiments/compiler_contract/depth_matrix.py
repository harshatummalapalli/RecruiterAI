"""Targeted test of the OBSERVED-DEPTH contract (real Judge model, SYNTHETIC profiles, 6 repetitions, no tuning between runs).

The Judge no longer answers "does this evidence meet hands-on Java?". For a skill + depth check the model reports `observed_depth` (unspecified / working_knowledge / hands_on /
advanced): what the supplied evidence DEMONSTRATES, never told the required depth. CODE then decides `observed_depth >= required_depth`.

Matrix: five evidence levels x three required depths, one profile per level, one intent with three skills, each required at a different depth:

    Power BI -> working_knowledge      Java -> hands_on      Microsoft Excel -> advanced

    evidence level                  expected observed depth      stronger than a requirement for
    none (named / title / years)    unspecified
    familiar (coursework only)      unspecified
    working_knowledge               working_knowledge
    hands_on                        hands_on                     Power BI (needs working knowledge)
    advanced                        advanced                     Power BI and Java

Declared BEFORE the run. PASS only if (A) the model's observed depth is the expected one in every cell and run, (B) the deterministic comparison is right in every cell
(by code, and end to end) and (C) every accepted depth observation has a quote that passes the gate, names the skill and comes from demonstrated work.

    python -m backend.experiments.compiler_contract.depth_matrix run [--runs 6]
    python -m backend.experiments.compiler_contract.depth_matrix analyze
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.experiments.compiler_contract import real_judge_run as rr
from backend.services import consumer_input as ci
from backend.services.evidence_check import DEPTH_ORDER, meets_depth, subject_in, verify_quote

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "depth_matrix"
RAW = RESULTS / "raw"

SKILLS: List[Tuple[str, str, str]] = [
    ("Power BI", "working_knowledge", "Working knowledge of Power BI is required."),
    ("Java", "hands_on", "Hands-on Java experience is required."),
    ("Microsoft Excel", "advanced", "Advanced Microsoft Excel skills are required."),
]
REQUIRED = {n: d for n, d, _q in SKILLS}


@dataclass(frozen=True)
class DepthProfile:
    key: str
    level: str                      # the depth the evidence demonstrates (expected observed depth) for all three skills
    label: str
    title: str
    headline: str
    start_year: int
    passages: Tuple[str, ...]
    skills: Tuple[str, ...] = ()


PROFILES: List[DepthProfile] = [
    DepthProfile("none", "unspecified", "named only: a skills list, a title, a headline, years of experience and generic verbs", "Java Developer",
                 "Java Developer | Power BI | Excel | 9 years of experience", 2015, (
                     "SYNTHETIC PROFILE. Senior Analyst at Reed Partners (fictional), 2015 to present, with 9 years of experience. Responsible for reporting and spreadsheets and "
                     "worked on Java, Power BI and Microsoft Excel projects with the technology team.",), ("Java", "Power BI", "Microsoft Excel")),
    DepthProfile("familiar", "unspecified", "familiar from coursework only; never used in a job", "Graduate Trainee", "Graduate Trainee", 2024, (
        "SYNTHETIC PROFILE. Graduate trainee. Studied Java, Power BI and Microsoft Excel in university courses and is familiar with all three. Has not used any of them in a job.",)),
    DepthProfile("working_knowledge", "working_knowledge", "real but modest use", "Operations Analyst", "Operations Analyst", 2019, (
        "SYNTHETIC PROFILE. Operations Analyst at Cove Logistics (fictional), 2019 to present. Uses Microsoft Excel for everyday tasks such as sums, simple formulas and charts. "
        "Has assembled a few dashboards from templates in Power BI and updated small Java utility scripts when asked, with working knowledge of each.",)),
    DepthProfile("hands_on", "hands_on", "builds with each as a core part of the job", "Backend Engineer", "Backend Engineer", 2017, (
        "SYNTHETIC PROFILE. Backend Engineer at Alder Systems (fictional), 2017 to present. Writes and ships production Java services every day. Builds the team's Power BI "
        "reports and their data models each month. Builds the budget and forecast workbooks in Microsoft Excel from scratch.",)),
    DepthProfile("advanced", "advanced", "stated expertise and sophisticated work with each", "Principal Engineer", "Principal Engineer", 2012, (
        "SYNTHETIC PROFILE. Principal Engineer at Fenwick Labs (fictional), 2012 to present. Advanced Java expert: designs the JVM performance tuning, concurrency architecture and "
        "garbage-collection strategy for high-throughput services. Builds advanced Power BI solutions: DAX measures, star-schema semantic models, incremental refresh and "
        "row-level security. Advanced Microsoft Excel user: dynamic driver-based financial models with VBA macros, Power Pivot data models and array formulas.",)),
]


def depth_intent():
    jd = " ".join(q for _n, _d, q in SKILLS)
    skills = [{"name": n, "strength": "required", "proficiency": d, "basis": {"sources": ["jd"], "quote": q}} for n, d, q in SKILLS]
    return ci.search_intent_for_context(rr.conflict_context(jd, skills=skills))


def expected_verdict(level: str, required: str) -> str:
    """The truth table, independent of the Judge: met iff the evidence's depth >= the required depth; demonstrated but below is partly; undemonstrated is not_evidenced."""
    if DEPTH_ORDER[level] >= DEPTH_ORDER[required]:
        return "met"
    return "partly" if level != "unspecified" else "not_evidenced"


def _path(key: str, run: int) -> Path:
    return RAW / f"DM__{key}__run{run}.json"


def run(runs: int = 6, workers: int = 6, model: str = None, raw: Path = None) -> None:
    """`model` / `raw` select a different Judge model and result directory; the matrix, the checks, the prompts and the evaluator are the same."""
    raw = raw or RAW
    raw.mkdir(parents=True, exist_ok=True)
    intent = depth_intent()
    path = lambda key, run_: raw / f"DM__{key}__run{run_}.json"                                   # noqa: E731
    tasks = [(p, k) for p in PROFILES for k in range(1, runs + 1) if not path(p.key, k).exists()]
    print(f"{len(tasks)} judge runs to do (model {model or 'production default'})", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(rr.run_one, "DM", p, "depth", intent, k, model): (p, k) for p, k in tasks}
        for i, f in enumerate(as_completed(futs), 1):
            j = f.result()
            p, k = futs[f]
            path(p.key, k).write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"[{i}/{len(tasks)}] {p.key} run{k} failed={j['failed']} {j['seconds']}s", flush=True)


def load(raw: Path = RAW) -> List[Dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(raw.glob("DM__*.json"))]


def _passages(job: Dict[str, Any]) -> List[Dict[str, str]]:
    for r in job["requests"]:
        if r["system"].startswith("You read a candidate's profile and report how deeply"):
            return json.loads(r["user"])["passages"]
    return []


def analyze(raw: Path = RAW, write: bool = True) -> Dict[str, Any]:
    jobs = load(raw)
    cells: List[Dict[str, Any]] = []
    prof = {p.key: p for p in PROFILES}
    for j in jobs:
        level = prof[j["candidate"]].level
        by_id = {c["check_id"]: c for c in j["checks"]}
        passages = _passages(j)
        for x in j["judgments"]:
            c = by_id[x["check_id"]]
            if c["kind"] != "proficiency":
                continue
            req = c["proficiency"]
            claimed = x.get("claimed_depth") or "unspecified"
            accepted = x.get("observed_depth") or "unspecified"
            truth = expected_verdict(level, req)
            # B (code): the verdict is exactly what the ordinal comparison gives for the ACCEPTED observed depth (recomputed here, independently of the Judge)
            code_verdict = "met" if meets_depth(accepted, req) else ("partly" if accepted != "unspecified" else "not_evidenced")
            c_ok, c_why = True, ""
            if accepted != "unspecified":
                if not any(verify_quote(x["quote"], p["text"])[0] for p in passages):
                    c_ok, c_why = False, "quote fails the gate"
                elif c["subject_terms"] and not subject_in(x["quote"], tuple(c["subject_terms"])):
                    c_ok, c_why = False, "quote does not name the skill"
                elif x.get("evidence_type") not in ("demonstrated_work", "certification"):
                    c_ok, c_why = False, "not demonstrated work"
            cells.append({"profile": j["candidate"], "run": j["run"], "skill": c["subject"], "required": req, "expected_depth": level, "claimed": claimed, "accepted": accepted,
                          "A_model_correct": claimed == level, "A_final_correct": accepted == level, "verdict": x["verdict"], "code_verdict": code_verdict,
                          "B_code_correct": x["verdict"] == code_verdict, "truth_verdict": truth, "B_end_to_end_correct": (x["verdict"] == "met") == (truth == "met"),
                          "stronger_than_required": DEPTH_ORDER[level] > DEPTH_ORDER[req], "C_ok": c_ok, "C_why": c_why, "discard": x.get("discard_reason")})
    n = len(cells)
    agg = lambda k: sum(1 for c in cells if c[k])                                            # noqa: E731
    stronger = [c for c in cells if c["stronger_than_required"]]
    by_cell: Dict[str, Dict[str, Any]] = {}
    for c in cells:
        k = f"{c['profile']}|{c['skill']}"
        d = by_cell.setdefault(k, {"profile": c["profile"], "skill": c["skill"], "required": c["required"], "expected_depth": c["expected_depth"], "truth": c["truth_verdict"],
                                   "runs": 0, "claimed": {}, "accepted": {}, "verdicts": {}, "A": 0, "B_e2e": 0, "B_code": 0, "C": 0})
        d["runs"] += 1
        for fld, key in (("claimed", "claimed"), ("accepted", "accepted"), ("verdicts", "verdict")):
            d[fld][c[key]] = d[fld].get(c[key], 0) + 1
        d["A"] += c["A_model_correct"]
        d["B_e2e"] += c["B_end_to_end_correct"]
        d["B_code"] += c["B_code_correct"]
        d["C"] += c["C_ok"]
    t = {"jobs": len(jobs), "cells": n, "calls": sum(j["calls"] for j in jobs), "input_tokens": sum(j["input_tokens"] for j in jobs), "output_tokens": sum(j["output_tokens"] for j in jobs),
         "estimated_cost_usd": round(sum(j["estimated_cost_usd"] for j in jobs), 4), "failed_jobs": sum(1 for j in jobs if j["failed"]), "models": sorted({j["model"] for j in jobs}),
         "temperatures": sorted({str(r["temperature"]) for j in jobs for r in j["requests"]}), "retried_checks": sum(len(j["retries"]["requirement"]) for j in jobs),
         "retries_recovered": sum(1 for j in jobs for r in j["retries"]["requirement"] if r["recovered"]), "binding_discards": sum(len(j["binding_discards"]) for j in jobs)}
    # what the model was sent in the depth pass: the skills only, never the required depth
    payload_leaks = 0
    for j in jobs:
        for r in j["requests"]:
            if r["system"].startswith("You read a candidate's profile and report how deeply"):
                body = json.loads(r["user"])
                if set(body) - {"passages", "skills", "instruction"} or any(set(sk) != {"d", "skill"} for sk in body["skills"]):
                    payload_leaks += 1
    leaks = sum(1 for j in jobs for r in j["requests"] for tok in rr.LEAK_TOKENS if tok.casefold() in r["user"].casefold())
    errs = [c for c in cells if not c["A_model_correct"]]
    dist = lambda c: DEPTH_ORDER[c["claimed"]] - DEPTH_ORDER[c["expected_depth"]]                  # noqa: E731
    error_profile = {"errors": len(errs), "over_by_one_level": sum(1 for c in errs if dist(c) == 1), "under_by_one_level": sum(1 for c in errs if dist(c) == -1),
                     "two_or_more_levels": sum(1 for c in errs if abs(dist(c)) >= 2),
                     "by_skill": {k: sum(1 for c in errs if c["skill"] == k) for k in REQUIRED}, "by_evidence_level": {p.level + "/" + p.key: sum(1 for c in errs if c["profile"] == p.key) for p in PROFILES},
                     "cells_wrong_on_every_run": sum(1 for d in by_cell.values() if d["A"] == 0), "cells_right_on_every_run": sum(1 for d in by_cell.values() if d["A"] == d["runs"]), "cells": len(by_cell)}
    summary = {"error_profile": error_profile, "totals": t, "A_model_observed_depth": {"correct": agg("A_model_correct"), "of": n}, "A_final_observed_depth": {"correct": agg("A_final_correct"), "of": n},
               "B_code_comparison": {"correct": agg("B_code_correct"), "of": n}, "B_end_to_end_verdict": {"correct": agg("B_end_to_end_correct"), "of": n},
               "B_stronger_than_required": {"correct": sum(1 for c in stronger if c["B_end_to_end_correct"]), "of": len(stronger)},
               "C_quote_binding": {"ok": agg("C_ok"), "of": n, "violations": [c for c in cells if not c["C_ok"]]},
               "depth_payload_violations": payload_leaks, "leak_token_hits": leaks, "cells": sorted(by_cell.values(), key=lambda d: (list(DEPTH_ORDER).index(d["expected_depth"]), d["skill"]))}
    summary["passed"] = (summary["A_model_observed_depth"]["correct"] == n and summary["B_code_comparison"]["correct"] == n and summary["B_end_to_end_verdict"]["correct"] == n
                         and not summary["C_quote_binding"]["violations"] and payload_leaks == 0 and leaks == 0 and n == 90)
    if write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "analyze"])
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.runs, a.workers)
    else:
        s = analyze()
        print(json.dumps({k: v for k, v in s.items() if k not in ("cells",)}, indent=1, default=str)[:3000])
        for c in s["cells"]:
            print(c["expected_depth"], c["skill"], "req", c["required"], "claimed", c["claimed"], "verdicts", c["verdicts"], "A", c["A"], "/", c["runs"])
