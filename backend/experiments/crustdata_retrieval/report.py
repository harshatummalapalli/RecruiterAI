"""Comparison tables for experiment crustdata-nl-vs-structured-20260924 (no network).
Writes analysis.json into the experiment store and prints the tables."""

import json
import statistics
from typing import Any, Dict, List

from backend.experiments.crustdata_retrieval import run as exp
from backend.experiments.crustdata_retrieval.analysis import fit_distribution, fit_position_correlation, overlap

STRONG_CORE_SHARE = 0.6   # "strong" = evidence for at least 60% of the core requirements, excluding the shared years line


def _mean(values: List[float]) -> float:
    return round(statistics.mean(values), 2) if values else 0.0


def evidence_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    core_total = rows[0]["requirement_totals"]["core"]
    non_years_core_total = max(1, core_total - (1 if any(q["requirement"].lower().startswith(("3+", "5+", "6+", "7+", "8+")) or "years" in q["requirement"].lower() for r in rows for q in r["quotes"] if False) else 0))
    strong = [r for r in rows if r["core_met_excluding_dates"] >= STRONG_CORE_SHARE * core_total]
    return {
        "n": len(rows),
        "harvest_read": sum(r["harvest_read"] for r in rows),
        "avg_core_met_excl_dates": _mean([r["core_met_excluding_dates"] for r in rows]),
        "avg_supporting_met": _mean([r["met"]["supporting"] for r in rows]),
        "avg_differentiator_met": _mean([r["met"]["differentiator"] for r in rows]),
        "avg_demonstrated_evidence": _mean([r["demonstrated_evidence"] for r in rows]),
        "avg_listed_only_evidence": _mean([r["listed_only_evidence"] for r in rows]),
        "no_evidence_beyond_years": sum(1 for r in rows if r["met_excluding_career_dates"] == 0),
        "strong_candidates": len(strong),
        "level_fit": {k: sum(1 for r in rows if r["level_fit"] == k) for k in ("aligned", "above", "below", "unclear")},
        "floor_met": sum(1 for r in rows if r["experience_floor"] is True),
        "with_concerns": sum(1 for r in rows if r["concerns"]),
        "avg_existing_score_descriptive": _mean([r["existing_release1_score_descriptive_only"] for r in rows]),
    }


def build() -> Dict[str, Any]:
    manifest = exp._load("manifest.json")
    out: Dict[str, Any] = {"experiment_id": exp.EXPERIMENT_ID, "roles": {}}
    for role in manifest["roles"]:
        key = role["role_key"]
        nl = exp._load(f"retrieval_{key}_nl.json")
        st = exp._load(f"retrieval_{key}_structured.json")
        ev = exp._load(f"evaluation_{key}.json")
        a_ids = [r["candidate_id"] for r in nl["rows"]]
        b_ids = [r["candidate_id"] for r in st["rows"]]
        shared = set(a_ids) & set(b_ids)
        entry: Dict[str, Any] = {
            "label": role["label"],
            "nl": {"retrieved": len(a_ids), "universe_provider_reported": nl["total_count_provider_reported_search_universe"], "total_count_relation": nl["response_envelope"].get("total_count_relation"),
                   "fit_all": fit_distribution(nl["rows"]), "fit_top10": fit_distribution(nl["rows"], 10), "fit_top25": fit_distribution(nl["rows"], 25),
                   "fit_position_spearman": fit_position_correlation(nl["rows"]), "has_cursor": bool(nl["next_cursor"])},
            "structured": {"retrieved": len(b_ids), "universe_provider_reported": st["total_count_provider_reported_search_universe"], "total_count_relation": st["response_envelope"].get("total_count_relation"),
                           "fit_all": fit_distribution(st["rows"]), "has_cursor": bool(st["next_cursor"])},
            "overlap_top50": overlap(a_ids, b_ids),
            "overlap_top10": overlap(a_ids[:10], b_ids[:10]),
            "overlap_top25": overlap(a_ids[:25], b_ids[:25]),
            "unrepresented_requirements": len(role["structured"]["structured_unrepresented_requirement"]),
            "evidence": {},
        }
        by = {}
        for strategy in ("nl", "structured"):
            rows = sorted([r for r in ev if r["strategy"] == strategy], key=lambda r: r["provider_position"])
            by[strategy] = rows
            entry["evidence"][strategy] = {"top10": evidence_summary(rows[:10]), "top25": evidence_summary(rows[:25])}
        entry["evidence"]["nl_only_top10"] = evidence_summary([r for r in by["nl"] if r["candidate_id"] not in shared][:10])
        entry["evidence"]["structured_only_top10"] = evidence_summary([r for r in by["structured"] if r["candidate_id"] not in shared][:10])
        entry["evidence"]["shared"] = evidence_summary([r for r in by["nl"] if r["candidate_id"] in shared])
        # strong candidates found by only one strategy (top 25 of each)
        core_total = by["nl"][0]["requirement_totals"]["core"] if by["nl"] else 0
        def strong(rows):
            return [r for r in rows if r["core_met_excluding_dates"] >= STRONG_CORE_SHARE * core_total and r["core_met_excluding_dates"] > 0]
        entry["strong_nl_only"] = [{k: r[k] for k in ("candidate_id", "provider_position", "current_title", "core_met_excluding_dates", "demonstrated_evidence", "level_fit")} for r in strong(by["nl"]) if r["candidate_id"] not in shared]
        entry["strong_structured_only"] = [{k: r[k] for k in ("candidate_id", "provider_position", "current_title", "core_met_excluding_dates", "demonstrated_evidence", "level_fit")} for r in strong(by["structured"]) if r["candidate_id"] not in shared]
        out["roles"][key] = entry
    exp._dump("analysis.json", out)
    return out


def show() -> None:
    out = build()
    for key, e in out["roles"].items():
        print(f"\n=== {e['label']}")
        print(" NL         retrieved", e["nl"]["retrieved"], "| universe", e["nl"]["universe_provider_reported"], e["nl"]["total_count_relation"], "| fit", e["nl"]["fit_all"], "| top10", e["nl"]["fit_top10"], "| rho", e["nl"]["fit_position_spearman"])
        print(" STRUCTURED retrieved", e["structured"]["retrieved"], "| universe", e["structured"]["universe_provider_reported"], "| fit", e["structured"]["fit_all"])
        o = e["overlap_top50"]; print(f" OVERLAP top50: inter={o['intersection']} nl_only={o['a_only']} st_only={o['b_only']} jaccard={o['jaccard']} | top10 inter={e['overlap_top10']['intersection']} top25 inter={e['overlap_top25']['intersection']}")
        for label in ("nl", "structured"):
            for depth in ("top10", "top25"):
                s = e["evidence"][label][depth]
                print(f"  {label:10} {depth}: n={s['n']} read={s['harvest_read']} core={s['avg_core_met_excl_dates']} supp={s['avg_supporting_met']} diff={s['avg_differentiator_met']} demo={s['avg_demonstrated_evidence']} listed={s['avg_listed_only_evidence']} noEvid={s['no_evidence_beyond_years']} strong={s['strong_candidates']} level={s['level_fit']} concerns={s['with_concerns']}")
        for label in ("nl_only_top10", "structured_only_top10", "shared"):
            s = e["evidence"][label]
            if s: print(f"  {label:22} n={s['n']} core={s['avg_core_met_excl_dates']} supp={s['avg_supporting_met']} diff={s['avg_differentiator_met']} demo={s['avg_demonstrated_evidence']} noEvid={s['no_evidence_beyond_years']} strong={s['strong_candidates']}")
        print("  strong NL-only:", len(e["strong_nl_only"]), "| strong structured-only:", len(e["strong_structured_only"]))


if __name__ == "__main__":
    show()
