"""Runs the REAL Judge (production model, unchanged requirement and review prompts) on the three Evidence Check scenarios, 6 runs each, no tuning between runs, and
analyses them against the acceptance rules.

    python -m backend.experiments.compiler_contract.evidence_check_run run [--runs 6]
    python -m backend.experiments.compiler_contract.evidence_check_run analyze

Only OpenAI (the Judge's own model) is called. No CrustData, no Harvest, no retrieval, no real candidate data.
"""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.experiments.compiler_contract import evidence_check_scenarios as scn
from backend.experiments.compiler_contract import real_judge_run as rr
from backend.services.evidence_check import RETRIABLE_QUOTE_FAILURES, subject_in, verify_quote

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "evidence_check"
RAW = RESULTS / "raw"
LEAK_TOKENS = tuple(rr.LEAK_TOKENS) + ("check_id", "recruiter_wording", "evidence_terms", "exclusion-predicates")


def table() -> Dict[str, Any]:
    base = rr.scenario_table()
    out = {}
    for g, (profiles, expects, (role, ctx)) in scn.SCENARIOS.items():
        out[g] = {"profiles": profiles, "expects": expects, "intent": base[role]["contexts"][ctx], "context": ctx, "role": role}
    return out


def _path(group: str, cand: str, run: int) -> Path:
    return RAW / f"EC{group}__{cand}__run{run}.json"


def run(runs: int, workers: int = 6) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    tasks = []
    for g, spec in table().items():
        for p in spec["profiles"]:
            for k in range(1, runs + 1):
                if not _path(g, p.key, k).exists():                      # resumable; a finished run is never re-run (so never re-tuned)
                    tasks.append((g, p, spec["context"], spec["intent"], k))
    print(f"{len(tasks)} judge runs to do", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(rr.run_one, f"EC{g}", p, ctx, intent, k): (g, p.key, k) for g, p, ctx, intent, k in tasks}
        for f in as_completed(futs):
            j = f.result()
            g, c, k = futs[f]
            _path(g, c, k).write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            done += 1
            print(f"[{done}/{len(tasks)}] EC{g} {c} run{k} failed={j['failed'] or j['exclusion_failed']} {j['seconds']}s ${j['estimated_cost_usd']}", flush=True)


# ------------------------------------------------------------------------------------------------------------------------------ exploratory diagnostic

DIAG = RESULTS / "diagnostics_at_least"
AT_LEAST = {
    "hands_on": "at least the level of hands-on use (a deeper level also satisfies it). The candidate has personally built, written or operated {s} in real work. Listing {s} as a skill, "
                "having studied it, or working beside people who use it is not hands-on use.",
    "working_knowledge": "at least the level of working knowledge (a deeper level, such as advanced use, also satisfies it). The candidate has practical familiarity with {s} from actual use. "
                         "A listed skill or a course alone is not enough.",
    "advanced": "at the level of advanced proficiency. The candidate shows depth beyond routine use of {s} (stated expertise, or sophisticated work built with it). Routine or basic use is not advanced.",
}


def diagnose_at_least(runs: int = 6, workers: int = 6) -> None:
    """EXPLORATORY, NOT PART OF THE VALIDATION, NOT ADOPTED. Tests ONE hypothesis about why C3 (basic Excel + ADVANCED Power BI) never met a working-knowledge check: the
    criterion names a level without saying a deeper level also satisfies it. Re-runs scenario C only, with the depth clause worded 'at least'. The production wording is unchanged."""
    from backend.services import evidence_check as ec
    DIAG.mkdir(parents=True, exist_ok=True)
    spec = table()["C"]
    saved = dict(ec.DEPTH_CLAUSE)
    ec.DEPTH_CLAUSE.update(AT_LEAST)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(rr.run_one, "ECCx", p, spec["context"], spec["intent"], k) for p in spec["profiles"] for k in range(1, runs + 1)]
            for f in as_completed(futs):
                j = f.result()
                (DIAG / f"{j['group']}__{j['candidate']}__run{j['run']}.json").write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    finally:
        ec.DEPTH_CLAUSE.clear()
        ec.DEPTH_CLAUSE.update(saved)


# ------------------------------------------------------------------------------------------------------------------------------ analysis


def load(raw: Path = RAW) -> List[Dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(raw.glob("EC*.json"))]


def _first_requests(job: Dict[str, Any], prefix: str) -> List[Dict[str, Any]]:
    return [r for r in job["requests"] if r["system"].startswith(prefix)]


REQ_PREFIX, EXC_PREFIX = "You verify whether a candidate's profile shows evidence", "You check whether a candidate's profile shows an EXCLUDED"


def _passage_texts(job: Dict[str, Any]) -> List[str]:
    for r in job["requests"]:
        if r["system"].startswith((REQ_PREFIX, EXC_PREFIX)):
            return [p["text"] for p in json.loads(r["user"])["passages"]]
    return []


def _check_for(job: Dict[str, Any], label: str, polarity: str = "positive") -> Optional[Dict[str, Any]]:
    return next((c for c in (job["checks"] or []) if c["polarity"] == polarity and (c["label"] == label or (polarity == "negative" and c["label"].startswith(label)))), None)


def evaluate(e, job: Dict[str, Any]) -> tuple:
    """(ok, observed). Also enforces, for the verdict it looks at, that it is bound to the RIGHT check_id and that its quote passes the gate and the binding."""
    if e.kind == "excl_state":
        chk = next((c for c in (job["checks"] or []) if c["polarity"] == "negative" and c["label"].startswith(e.item)), None)
        x = next((x for x in (job["exclusion_judgments"] or []) if chk and x["check_id"] == chk["check_id"]), None)
        if x is None:
            return False, "no verdict bound to this check_id"
        if x["state"] == "PRESENT":
            ok_q = any(verify_quote(x["quote"], t)[0] for t in _passage_texts(job))
            terms = (chk["predicate"] or {}).get("evidence_terms") or []
            bound = any(subject_in(x["quote"], tuple(re.findall(r"[a-z0-9]+", t.casefold()))) for t in terms) if terms else True
            if not (ok_q and bound):
                return False, f"PRESENT without a gate-passing, indicator-bound quote (quote ok={ok_q}, bound={bound})"
        return x["state"] == e.other, x["state"]
    chk = _check_for(job, e.item)
    if chk is None:
        return False, "check missing"
    j = next((j for j in (job["judgments"] or []) if j.get("check_id") == chk["check_id"]), None)
    if j is None:
        return False, "no verdict bound to this check_id"
    if j["verdict"] == "met":
        if not any(verify_quote(j["quote"], t)[0] for t in _passage_texts(job)):
            return False, "met without a gate-passing quote"
        if chk["subject_terms"] and not subject_in(j["quote"], tuple(chk["subject_terms"])):
            return False, "met on a quote that does not name the check's subject"
        if chk["requires_work_evidence"] and j.get("evidence_type") not in ("demonstrated_work", "certification"):
            return False, "a depth claim met on non-work evidence"
    if e.kind == "req_met":
        return j["verdict"] == "met", j["verdict"] + (f" ({j['discard_reason']})" if j.get("discard_reason") else "") + (f" [{j['review']}]" if j.get("review") else "")
    if e.kind == "req_not_met":
        return j["verdict"] != "met", j["verdict"] + (f" ({j['discard_reason']})" if j.get("discard_reason") else "")
    raise ValueError(e.kind)


def universal(job: Dict[str, Any]) -> Dict[str, Any]:
    """The rules that must hold on EVERY run, independent of any scenario."""
    out: Dict[str, Any] = {"unbound": [], "bad_quotes": [], "binding_violations": [], "retry_violations": [], "leaks": []}
    checks = job["checks"] or []
    ids = [c["check_id"] for c in checks]
    if len(ids) != len(set(ids)):
        out["unbound"].append("duplicate check_id")
    by_id = {c["check_id"]: c for c in checks}
    texts = _passage_texts(job)
    for j in job["judgments"] or []:
        if j.get("check_id") not in by_id:
            out["unbound"].append(f"judgment without a known check_id: {j['signal_text'][:40]}")
        if j["verdict"] in ("met", "partly") and not j.get("deterministic") and j.get("source") != "career dates":
            if not any(verify_quote(j["quote"], t)[0] for t in texts):
                out["bad_quotes"].append((j.get("check_id"), j["quote"][:60]))
            c = by_id.get(j.get("check_id"))
            if c and c["subject_terms"] and not subject_in(j["quote"], tuple(c["subject_terms"])):
                out["binding_violations"].append((c["check_id"], j["quote"][:60]))
            if c and c["requires_work_evidence"] and j.get("evidence_type") not in ("demonstrated_work", "certification"):
                out["binding_violations"].append((c["check_id"], "non-work evidence for a depth claim"))
    for x in job["exclusion_judgments"] or []:
        if x.get("check_id") not in by_id:
            out["unbound"].append(f"exclusion without a known check_id: {x['text'][:40]}")
        if x["state"] == "PRESENT" and not any(verify_quote(x["quote"], t)[0] for t in texts):
            out["bad_quotes"].append((x["check_id"], x["quote"][:60]))
        if x["state"] not in ("PRESENT", "NOT_PRESENT", "INSUFFICIENT_EVIDENCE"):
            out["unbound"].append(f"unknown state {x['state']}")
    # the retry: only checks whose first pass failed the quote gate; once per pass; never a successful check
    pos = [c for c in checks if c["polarity"] == "positive"]
    neg = [c for c in checks if c["polarity"] == "negative"]
    rq = {r["check_id"] for r in job["retries"]["requirement"]}
    rx = {r["check_id"] for r in job["retries"]["exclusion"]}
    for pre, key, listing, allowed in ((REQ_PREFIX, "requirements", pos, rq), (EXC_PREFIX, "exclusion_checks", neg, rx)):
        calls = [r for r in job["requests"] if r["system"].startswith(pre)]
        retry_calls = [r for r in calls if "instruction" in json.loads(r["user"])]
        if len(retry_calls) > 1:
            out["retry_violations"].append(f"{len(retry_calls)} retry calls in one pass")
        for r in retry_calls:
            payload = json.loads(r["user"])
            idx = [q.get("r", q.get("x")) for q in payload[key]]
            sent = {listing[i]["check_id"] for i in idx}
            if sent != allowed:
                out["retry_violations"].append(f"retry payload {sorted(sent)} != recorded failures {sorted(allowed)}")
    for r in job["retries"]["requirement"] + job["retries"]["exclusion"]:
        if r["first_pass_failure"] not in RETRIABLE_QUOTE_FAILURES:
            out["retry_violations"].append(f"retried a non-quote failure: {r['first_pass_failure']}")
    for r in job["requests"]:
        blob = r["user"].casefold()
        for t in LEAK_TOKENS:
            if t.casefold() in blob:
                out["leaks"].append(t)
    return out


def analyze(raw: Path = RAW, write: bool = True) -> Dict[str, Any]:
    jobs = load(raw)
    spec = table()
    scenarios: Dict[str, Any] = {}
    exp_rows: List[Dict[str, Any]] = []
    uni_viol = {k: 0 for k in ("unbound", "bad_quotes", "binding_violations", "retry_violations", "leaks")}
    for j in jobs:
        for k, v in universal(j).items():
            uni_viol[k] += len(v)
    for g, s in spec.items():
        gating = [e for e in s["expects"] if not e.eid.endswith("-info")]
        per_run: Dict[int, List[bool]] = {}
        for e in s["expects"]:
            rs = sorted((j for j in jobs if j["group"] == f"EC{g}" and j["candidate"] == e.candidate), key=lambda j: j["run"])
            res = [evaluate(e, j) for j in rs]
            ok = [r[0] for r in res]
            exp_rows.append({"scenario": g, "eid": e.eid, "candidate": e.candidate, "check": e.kind, "item": e.item, "expected": e.other or ("met" if e.kind == "req_met" else "not met"),
                             "why": e.why, "gating": e in gating, "runs": len(ok), "passed_runs": sum(ok), "observed": [r[1] for r in res],
                             "status": "NOT RUN" if not ok else "PASS" if all(ok) else "FAIL" if not any(ok) else "UNSTABLE"})
            if e in gating:
                for j, r in zip(rs, res):
                    per_run.setdefault(j["run"], []).append(r[0])
        runs_ok = sum(1 for v in per_run.values() if v and all(v))
        scenarios[g] = {"runs": len(per_run), "runs_all_correct": runs_ok, "expectations": sum(1 for e in gating)}
    # measurements of the mechanisms
    ell = said_ell = 0
    first_fail = rec = 0
    review_down = 0
    for j in jobs:
        for r in j["requests"]:
            if r["system"].startswith(REQ_PREFIX) and "instruction" not in json.loads(r["user"]) and r.get("response"):
                for x in json.loads(r["response"]).get("results", []):
                    if x.get("verdict") in ("met", "partly"):
                        said_ell += 1
                        ell += 1 if ("..." in str(x.get("quote")) or "…" in str(x.get("quote"))) else 0
        for r in j["retries"]["requirement"] + j["retries"]["exclusion"]:
            first_fail += 1
            rec += 1 if r["recovered"] else 0
        review_down += j["downgraded_by_review"]
    t = {"jobs": len(jobs), "calls": sum(j["calls"] for j in jobs), "input_tokens": sum(j["input_tokens"] for j in jobs), "output_tokens": sum(j["output_tokens"] for j in jobs),
         "estimated_cost_usd": round(sum(j["estimated_cost_usd"] for j in jobs), 3), "failed_jobs": sum(1 for j in jobs if j["failed"] or j["exclusion_failed"]),
         "models": sorted({j["model"] for j in jobs}), "temperatures": sorted({str(r["temperature"]) for j in jobs for r in j["requests"]}),
         "first_pass_claims_with_quote": said_ell, "first_pass_claims_with_ellipsis": ell, "retried_checks": first_fail, "retries_recovered": rec,
         "binding_discards": sum(len(j["binding_discards"]) for j in jobs), "review_downgrades": review_down,
         "retry_calls": sum(1 for j in jobs for r in j["requests"] if '"instruction"' in r["user"])}
    # what the deterministic binding discarded, by check (kind, subject tokens, reason), with an example quote
    bd: Dict[tuple, Dict[str, Any]] = {}
    for j in jobs:
        by_id = {c["check_id"]: c for c in (j["checks"] or [])}
        for d in j["binding_discards"]:
            c = by_id[d["check_id"]]
            k = (c["label"][:60], c["kind"], tuple(c["subject_terms"]), d["reason"])
            e = bd.setdefault(k, {"label": k[0], "kind": k[1], "subject_terms": list(k[2]), "reason": k[3], "count": 0, "example_quote": d["quote"][:80]})
            e["count"] += 1
    diag = {}
    if DIAG.exists():
        for f in sorted(DIAG.glob("*.json")):
            j = json.loads(f.read_text(encoding="utf-8"))
            for x in j["judgments"] or []:
                if x["signal_text"] in (scn.XL, scn.PBI):
                    diag.setdefault(j["candidate"], {}).setdefault("excel_advanced" if x["signal_text"] == scn.XL else "powerbi_working_knowledge", []).append(x["verdict"])
    summary = {"binding_breakdown": sorted(bd.values(), key=lambda e: -e["count"]), "diagnostic_at_least": diag, "totals": t, "universal_violations": uni_viol, "scenarios": scenarios, "expectations": exp_rows,
               "binding_discards": [{"job": f"{j['group']}/{j['candidate']}/run{j['run']}", **d} for j in jobs for d in j["binding_discards"]]}
    if write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "analyze", "diagnose_at_least"])
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.runs, a.workers)
    elif a.cmd == "diagnose_at_least":
        diagnose_at_least(a.runs, a.workers)
    else:
        s = analyze()
        print(json.dumps({k: s[k] for k in ("totals", "universal_violations", "scenarios")}, indent=1))
        for r in s["expectations"]:
            print(f"{r['status']:9} {r['eid']:18} {r['passed_runs']}/{r['runs']} {r['observed']}")
