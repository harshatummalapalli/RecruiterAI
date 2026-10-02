"""Phase 5.1 — credit-free re-evaluation over existing Phase-5 records.

No retrieval. Re-runs RequirementJudge (OpenAI, unchanged model/config) on the
ALREADY-SAVED candidate evidence, using the SAME compiler/structured semantic
requirements as the common evaluation intent for BOTH arms — so legacy vs
compiled are judged on identical criteria. Hard constraints are checked
deterministically from the saved evidence.

Run: python -m backend.experiments.phase5_compiler_ab.evaluate
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.models.candidate import Candidate
from backend.models.candidate_evidence import HarvestEvidence
from backend.models.search_intent import SearchIntent
from backend.services.requirement_judge import RequirementJudge

SEARCHES = Path("output/searches")
OUT = Path("output/experiments/phase5_compiler_ab")

RECORDS = {
    "epiq_legacy": "p5-epiq-legacy-05a323ae",
    "epiq_compiled": "p5-epiq-compiled-27128a9c",
    "python_compiled": "p5b-python-compiled-e223281a",
}

# Common evaluation intents = the compiler's semantic requirements. Same for
# both arms of a role.
EPIQ_CORE = ["Product vision and strategy", "Backlog ownership and Agile delivery", "Hands-on AI fluency"]
EPIQ_SUPPORTING = ["Stakeholder engagement", "Quality and risk management", "AI/ML product experience", "Legal technology domain knowledge"]
PY_CORE = ["Current hands-on Python development", "Prior Java development experience", "Django or FastAPI web framework"]


def _intent(core, supporting=None) -> SearchIntent:
    si = SearchIntent()
    si.core_signals = list(core)
    si.supporting_signals = list(supporting or [])
    si.differentiator_signals = []
    return si


def _load(sid: str) -> Dict[str, Any]:
    return json.loads((SEARCHES / f"{sid}.json").read_text(encoding="utf-8"))


def _candidates(rec: Dict[str, Any]):
    resp = rec["response"]
    ev = {e["candidate_id"]: e for e in (resp.get("evidence") or [])}
    harvest = {}
    for cid, payload in (rec.get("harvest_evidence") or {}).items():
        try:
            harvest[cid] = HarvestEvidence(**payload)
        except Exception:
            harvest[cid] = None
    out = []
    for c in resp.get("candidates") or []:
        try:
            cand = Candidate.model_validate(c)
        except Exception:
            cand = Candidate(candidate_id=c.get("candidate_id"), raw_data=c.get("raw_data"))
        out.append((cand, ev.get(c.get("candidate_id"), {}), harvest.get(c.get("candidate_id"))))
    return out


def _headcount(evidence_dict, cand) -> Optional[int]:
    cur = (((cand.raw_data or {}).get("experience") or {}).get("employment_details") or {}).get("current") or []
    return cur[0].get("company_headcount_latest") if cur else None


def _verdicts(judge: RequirementJudge, cand: Candidate, intent: SearchIntent, harvest) -> List[Dict[str, Any]]:
    try:
        js = judge.judge(cand, intent, harvest)
    except Exception as e:
        return [{"error": str(e)[:120]}]
    return js or []


def evaluate_arm(role: str, arm: str, sid: str, intent: SearchIntent, judge: RequirementJudge):
    rec = _load(sid)
    rows = []
    for cand, ev, harvest in _candidates(rec):
        ra = ev.get("role_alignment") or {}
        title = ev.get("current_title") or cand.title or ""
        company = ev.get("current_company") or cand.company or ""
        js = _verdicts(judge, cand, intent, harvest)
        met = [j for j in js if j.get("verdict") == "met"]
        core_met = [j for j in js if j.get("verdict") == "met" and j.get("tier") == "core"]
        is_role = ("product" in title.lower()) if role == "epiq" else any(k in title.lower() for k in ("software engineer", "developer", "sde", "backend"))
        # relevance from role-fit + re-judged core evidence
        if is_role and core_met:
            rel = "clearly_relevant"
        elif is_role or core_met:
            rel = "borderline"
        else:
            rel = "clearly_not_relevant"
        hard = []  # hard-constraint violations
        if role == "epiq" and "epiq" in company.lower():
            hard.append("currently at Epiq (exclusion)")
        rows.append({
            "id": cand.candidate_id, "title": title, "company": company, "level_fit": ra.get("level_fit"),
            "core_met": len(core_met), "supporting_met": len(met) - len(core_met),
            "met_signals": [j.get("signal_text") for j in met], "relevance": rel, "hard_violations": hard,
        })
    return {"role": role, "arm": arm, "search_id": sid, "candidates": rows}


def main():
    judge = RequirementJudge()
    if not judge.is_available():
        print("Judge unavailable (no OpenAI key)."); return
    results = []
    results.append(evaluate_arm("epiq", "legacy", RECORDS["epiq_legacy"], _intent(EPIQ_CORE, EPIQ_SUPPORTING), judge))
    results.append(evaluate_arm("epiq", "compiled", RECORDS["epiq_compiled"], _intent(EPIQ_CORE, EPIQ_SUPPORTING), judge))
    results.append(evaluate_arm("python", "compiled", RECORDS["python_compiled"], _intent(PY_CORE), judge))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eval_5_1.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    def summ(r):
        n = len(r["candidates"]);
        cr = sum(1 for c in r["candidates"] if c["relevance"] == "clearly_relevant")
        bd = sum(1 for c in r["candidates"] if c["relevance"] == "borderline")
        nr = sum(1 for c in r["candidates"] if c["relevance"] == "clearly_not_relevant")
        hv = sum(1 for c in r["candidates"] if c["hard_violations"])
        return n, cr, bd, nr, hv
    print(f"{'role/arm':22} {'N':>3} {'clear':>5} {'bord':>5} {'notrel':>6} {'hardviol':>8}")
    for r in results:
        n, cr, bd, nr, hv = summ(r)
        print(f"{r['role']+'/'+r['arm']:22} {n:>3} {cr:>5} {bd:>5} {nr:>6} {hv:>8}")
    # overlap (epiq)
    el = {c["id"] for c in results[0]["candidates"]}; ec = {c["id"] for c in results[1]["candidates"]}
    print(f"\nEPIQ overlap: both={len(el & ec)} legacy_only={len(el - ec)} compiled_only={len(ec - el)}")
    print("saved:", OUT / "eval_5_1.json")


if __name__ == "__main__":
    main()
