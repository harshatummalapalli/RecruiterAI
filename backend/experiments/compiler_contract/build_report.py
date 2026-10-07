"""Generate the TABLES of RESULTS_COMPILER_CONTRACT.md from results/contract_analysis.json (so no number is transcribed by hand).

    python -m backend.experiments.compiler_contract.build_report

The narrative lives in report_template.md; `{{name}}` placeholders are replaced with generated tables. Nothing here compiles or calls anything."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
ROLES = ("R1", "R2", "R3")
RNAME = {"R1": "Role 1", "R2": "Role 2", "R3": "Role 3"}


def md(rows: List[List[Any]], head: List[str]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in r) + " |")
    return "\n".join(out)


def fates_str(c: Counter) -> str:
    return ", ".join(f"{k}×{v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))


def load() -> Dict[str, Any]:
    return json.loads((RES / "contract_analysis.json").read_text(encoding="utf-8"))


def runs_of(d, role):
    return {k: v for k, v in d["runs"].items() if k.startswith(role)}


def table_plans(d, base) -> str:
    rows = []
    for k, run in d["runs"].items():
        b = json.loads((RES / "baseline" / f"{k.replace('/', '_run')}.json").read_text(encoding="utf-8"))
        routes = Counter(r["route"] for r in b["audit"])
        kinds = Counter()
        for l in b["leaves"]:
            f = l[0]
            kinds["title" if f.endswith("current.title") else "location" if "location" in f else "experience" if f.startswith("years") else
                  "education" if f.startswith("education") else "skill text" if f.endswith(("description", "headline", "summary")) else "other"] += 1
        rows.append([k, len(b["leaves"]), ", ".join(f"{a} {n}" for a, n in sorted(kinds.items())),
                     routes.get("provider_hard_filter", 0), routes.get("downstream_evidence", 0), routes.get("context_or_evidence", 0),
                     routes.get("admission_level_fit", 0), len(b["downstream_checklist"]), len(b["fields_present_but_never_read"])])
    return md(rows, ["intent", "hard leaves", "what they are", "rows: provider", "rows: downstream", "rows: context", "rows: admission", "checklist items", "present-but-never-read field paths"])


def table_matrix(d) -> str:
    agg = defaultdict(Counter)
    kind = {}
    for k, run in d["runs"].items():
        role = k[:2]
        for a in run["atoms"]:
            agg[(a["concept_key"], role)][a["fate"]] += 1
            kind[a["concept_key"]] = a["kind"]
    concepts = sorted({c for c, _ in agg})
    rows = []
    for c in concepts:
        row = [f"`{c}`", kind[c]]
        for r in ROLES:
            row.append(fates_str(agg[(c, r)]) if (c, r) in agg else "–")
        rows.append(row)
    return md(rows, ["concept [strength, relationship]", "kind", "Role 1 (5 runs)", "Role 2 (5 runs)", "Role 3 (5 runs)"])


def silent_counts(d) -> Dict[str, Any]:
    c: Dict[str, Counter] = defaultdict(Counter)
    for k, run in d["runs"].items():
        for a in run["atoms"]:
            c[k[:2]][(a["kind"], a["fate"] == "SILENTLY_DROPPED")] += 1
    return c


def table_silent(d) -> str:
    sc = silent_counts(d)
    rows = []
    for r in ROLES:
        m_all = sc[r][("MEANING", True)] + sc[r][("MEANING", False)]
        rows.append([RNAME[r], m_all, sc[r][("MEANING", True)], f"{100 * sc[r][('MEANING', True)] / m_all:.0f}%", sc[r][("RECORD", True)], sc[r][("METADATA", True)]])
    tot_all = sum(sc[r][("MEANING", True)] + sc[r][("MEANING", False)] for r in ROLES)
    tot_drop = sum(sc[r][("MEANING", True)] for r in ROLES)
    rows.append(["**all**", tot_all, tot_drop, f"{100 * tot_drop / tot_all:.0f}%", sum(sc[r][("RECORD", True)] for r in ROLES), sum(sc[r][("METADATA", True)] for r in ROLES)])
    return md(rows, ["role (5 runs each)", "meaning atoms", "SILENTLY_DROPPED meaning atoms", "share", "decision records dropped", "metadata dropped"])


def table_silent_by_concept(d) -> str:
    c = defaultdict(lambda: Counter())
    for k, run in d["runs"].items():
        for a in run["atoms"]:
            if a["kind"] == "MEANING":
                c[a["concept"] + (" (in path)" if a["scope"] != "global" else "")][("drop" if a["fate"] == "SILENTLY_DROPPED" else "kept", k[:2])] += 1
    rows = []
    for concept, cnt in sorted(c.items()):
        drops = {r: cnt[("drop", r)] for r in ROLES}
        kept = {r: cnt[("kept", r)] for r in ROLES}
        if sum(drops.values()) == 0:
            continue
        rows.append([f"`{concept}`"] + [f"{drops[r]} of {drops[r] + kept[r]}" if drops[r] + kept[r] else "–" for r in ROLES])
    return md(rows, ["meaning concept (only those with a drop)", "Role 1", "Role 2", "Role 3"])


EXTENSION_CONCEPTS = {"domain", "semantic_exclusion", "skill.proficiency", "location.work_mode", "location.country", "location.remote",
                      "seniority.leadership", "seniority.alternatives", "sourcing_path"}


def origin(a: Dict[str, Any]) -> str:
    if a["concept"] in EXTENSION_CONCEPTS:
        return "extension field (not in the production schema)"
    if a["scope"] != "global":
        return "production-schema atom, but inside a sourcing path"
    return "production-schema atom in the global intent"


def table_origin(d) -> str:
    c: Dict[str, Counter] = defaultdict(Counter)
    ex: Dict[str, set] = defaultdict(set)
    for k, run in d["runs"].items():
        for a in run["atoms"]:
            if a["kind"] == "MEANING" and a["fate"] == "SILENTLY_DROPPED":
                o = origin(a)
                c[o][k[:2]] += 1
                ex[o].add(a["concept"] + (f" [{a['strength']}]" if a["concept"].startswith("education") else ""))
    rows = [[o, c[o]["R1"], c[o]["R2"], c[o]["R3"], sum(c[o].values()), ", ".join(sorted(ex[o]))] for o in sorted(c)]
    return md(rows, ["origin of the dropped atom", "Role 1", "Role 2", "Role 3", "all", "concepts"])


def table_checks(d, role) -> str:
    byid: Dict[str, List[str]] = defaultdict(list)
    text: Dict[str, str] = {}
    gap: Dict[str, str] = {}
    for k, run in d["runs"].items():
        if k.startswith(role):
            for c in run["checks"]:
                byid[c["id"]].append(c["result"])
                text[c["id"]] = c["check"]
                if c["gap_type"]:
                    gap[c["id"]] = c["gap_type"]
    rows = [[i, text[i], fates_str(Counter(v)), gap.get(i, "—")] for i, v in sorted(byid.items())]
    return md(rows, ["id", "check", "results over 5 runs", "gap type"])


def table_compact(d) -> str:
    agg = defaultdict(Counter)
    exp: Dict[Any, set] = defaultdict(set)
    gap: Dict[Any, Counter] = defaultdict(Counter)
    for k, run in d["runs"].items():
        role = k[:2]
        for a in run["atoms"]:
            key = (a["concept_key"], role)
            agg[key][a["fate"]] += 1
            exp[key] |= set(a["expected_fates"])
            if a["gap_type"]:
                gap[key][a["gap_type"]] += 1
    # Fate-correct rows whose cause the atom-level rule cannot see; each note comes from a check or a probe, not from a guess.
    cur = sum(c["evidence"]["frozen_validator_unsupported_current"] for k, run in d["runs"].items() if k.startswith("R2") for c in run["checks"] if c["id"] == "R2-07")
    fde = sum(1 for k, run in d["runs"].items() if k.startswith("R2") for c in run["checks"] if c["id"] == "R2-06" and c["result"] == "FAIL")
    notes = {
        ("skill [required, current]", "R2"): f"PROVENANCE / VALIDATION: {cur} of 32 `current` skills have no source support (R2-07)",
        ("role_family", "R2"): f"PROVENANCE / VALIDATION: analogy title is a hard title leaf in {fde}/5 runs (R2-06)",
        ("location.entry [required]", "R3"): "PROVENANCE / VALIDATION: the inferred state is enforced as a hard AND (R3-01)",
        ("skill [required, any]", "R1"): "CAPABILITY MAP: any-time probe field unmapped (never provider-enforceable)",
        ("skill [required, any]", "R2"): "CAPABILITY MAP: any-time probe field unmapped (never provider-enforceable)",
        ("skill [required, any]", "R3"): "CAPABILITY MAP: any-time probe field unmapped (never provider-enforceable)",
        ("seniority.value", "R1"): "wiring to the admission gate unverified",
        ("seniority.value", "R3"): "wiring to the admission gate unverified; TAXONOMY: 'Senior Manager' reads as `senior` downstream",
        ("education.degree [required]", "R3"): "TAXONOMY: literal degree string (R3-09)",
        ("education.stream [required]", "R3"): "TAXONOMY: literal 'Related discipline' stream (R3-09)",
    }
    rows = []
    for (c, r), cnt in sorted(agg.items()):
        g = gap[(c, r)]
        base_gap = g.most_common(1)[0][0] if g else None
        note = notes.get((c, r))
        text = "; ".join(x for x in (base_gap, note) if x) or "—"
        rows.append([f"`{c}`", r, fates_str(cnt), " / ".join(sorted(exp[(c, r)])), text])
    return md(rows, ["CONCEPT", "ROLE", "CURRENT FATE", "EXPECTED FATE", "GAP TYPE"])


def table_strength(d) -> str:
    sw = d["probes"]["strength_relationship_sweep"]
    rows = []
    for r in sw:
        if r["construct"] in ("skill", "skill_any_of", "company", "company_scale"):
            continue
        rows.append([r["construct"], r["strength"], r["hard_leaves"], (r["audit"][2] if r["audit"] else "NO AUDIT ROW")])
    simple = md(rows, ["construct", "strength", "provider hard leaves", "audit route"])
    rows2 = []
    for c in ("skill", "skill_any_of", "company", "company_scale"):
        for st in ("required", "preferred", "context"):
            cells = []
            for rel in ("current", "past", "any"):
                x = next(r for r in sw if r["construct"] == c and r["strength"] == st and r["relationship"] == rel)
                cells.append(f"{x['hard_leaves']} ({x['audit'][2].replace('provider_hard_filter', 'HARD').replace('downstream_evidence', 'downstream').replace('context_or_evidence', 'context')})")
            rows2.append([c, st] + cells)
    return simple + "\n\n" + md(rows2, ["construct", "strength", "relationship = current", "= past", "= any"])


def table_exposure(d) -> str:
    rows = [[f"{r['role']}/{r['run']}", r["hard_leaves_actual"], r["hard_leaves_if_relationship_omitted"]] for r in d["probes"]["omission_exposure"]]
    return md(rows, ["intent", "hard leaves as compiled", "hard leaves if `relationship` had been omitted on every skill and group"])


def table_paths(d) -> str:
    rows = []
    for k, run in d["runs"].items():
        if not k.startswith("R1"):
            continue
        p = run["paths"]
        for pp in p["paths"]:
            rows.append([k, pp["path"], ", ".join(f"{l[0].split('.')[-1]} {l[2][:28]}" for l in pp["needed_by_path_but_absent_from_plan"]) or "–",
                         ", ".join(f"{l[0].split('.')[-1]} {l[2][:28]}" for l in pp["in_plan_but_not_needed_by_path"]) or "–",
                         ", ".join(pp["rows_needed_by_path_absent_from_plan"]) or "–"])
    return md(rows, ["intent", "path", "provider leaves the PATH needs that the compiled plan lacks", "leaves the plan has that the path does not need", "audit rows the path needs that the plan lacks"])


def table_location(d) -> str:
    rows = [[r["case"], json.dumps(r["location"], ensure_ascii=False), "; ".join(f"{l[0].split('.')[-1]}={l[2]}" for l in r["leaves"]) or "NO LEAF AND NO AUDIT ROW"] for r in d["probes"]["location"]]
    return md(rows, ["case", "location fields", "provider leaves"])


def table_seniority(d) -> str:
    rows = [[r["value"], "yes" if r["compiler_carries_value_verbatim"] else "NO", r["audit_route"], r["in_seniority_json"],
             f"{r['downstream_level_marker'][1]} (rank {r['downstream_level_marker'][0]})" if r["downstream_level_marker"] else "none"] for r in d["probes"]["seniority"]]
    return md(rows, ["level string", "compiler carries it verbatim", "audit route", "in seniority.json", "downstream candidate-evidence level reader maps it to"])


def table_titles(d) -> str:
    rows = [[", ".join(r["role_family"]), len(r["retrieval_titles"]), ", ".join(r["retrieval_titles"])] for r in d["probes"]["titles"]]
    return md(rows, ["role_family in the intent", "hard title leaves", "titles in the provider filter"])


def numbers(d) -> Dict[str, Any]:
    sc = silent_counts(d)
    n = {}
    for r in ROLES:
        m_all = sc[r][("MEANING", True)] + sc[r][("MEANING", False)]
        n[r] = {"meaning": m_all, "dropped": sc[r][("MEANING", True)]}
    n["total_meaning"] = sum(n[r]["meaning"] for r in ROLES)
    n["total_dropped"] = sum(n[r]["dropped"] for r in ROLES)
    return n


def build() -> str:
    d = load()
    tpl = (HERE / "report_template.md").read_text(encoding="utf-8")
    nums = numbers(d)
    mapping = {
        "plans": table_plans(d, None), "matrix": table_matrix(d), "silent": table_silent(d), "silent_by_concept": table_silent_by_concept(d), "origin": table_origin(d),
        "checks_r1": table_checks(d, "R1"), "checks_r2": table_checks(d, "R2"), "checks_r3": table_checks(d, "R3"),
        "compact": table_compact(d), "strength": table_strength(d), "exposure": table_exposure(d), "paths": table_paths(d),
        "location": table_location(d), "seniority": table_seniority(d), "titles": table_titles(d),
        "total_meaning": nums["total_meaning"], "total_dropped": nums["total_dropped"],
        "pct_dropped": f"{100 * nums['total_dropped'] / nums['total_meaning']:.0f}",
    }
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", str(v))
    left = [m for m in __import__("re").findall(r"\{\{(\w+)\}\}", out)]
    assert not left, left
    (HERE / "RESULTS_COMPILER_CONTRACT.md").write_text(out, encoding="utf-8")
    return out


if __name__ == "__main__":
    build()
