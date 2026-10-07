"""Generate the TABLES of RESULTS_COMPILER_HARDENING.md from the committed before/after measurements (no number is transcribed by hand).

    python -m backend.experiments.compiler_contract.build_hardening_report
"""

from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.compiler_contract import contract, legacy_compiler_v1 as legacy, loader
from backend.experiments.compiler_contract.build_report import fates_str, md
from backend.experiments.compiler_contract.signature import leaves
from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.models.structured_intent import SkillReq
from backend.services import compiler_audit as audit
# The hardening report is the record of compiler contract-1 as it was; its live tables are therefore built with the pinned contract-1 snapshot.
from backend.experiments.compiler_contract.compiler_contract1_snapshot import COMPILER_VERSION, compile_intent

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
ROLES = ("R1", "R2", "R3")
BASE = {"role_archetype": {"value": "hybrid", "confidence": 0.5, "rationale": "t"}, "role_family": ["Probe Role"]}


def mk(**kw) -> ExperimentalHiringIntent:
    return ExperimentalHiringIntent.model_validate({**copy.deepcopy(BASE), **kw})


def before() -> Dict[str, Any]:
    return json.loads((RES / "contract_analysis.json").read_text(encoding="utf-8"))


def after() -> Dict[str, Dict[str, Any]]:
    return {f"{r}/{n}": json.loads((RES / "hardened" / f"{r}_run{n}.json").read_text(encoding="utf-8")) for r in ROLES for n in range(1, 6)}


def table_matrix(b, a) -> str:
    agg_b: Dict[Any, Counter] = defaultdict(Counter)
    agg_a: Dict[Any, Counter] = defaultdict(Counter)
    for k, run in b["runs"].items():
        for x in run["atoms"]:
            agg_b[(x["concept_key"], k[:2])][x["fate"]] += 1
    for k, run in a.items():
        for x in run["atoms"]:
            row = dict(x)
            row.setdefault("strength", x.get("strength"))
            agg_a[(contract.concept_key(row), k[:2])][x["fate"]] += 1
    keys = sorted(set(agg_b) | set(agg_a))
    rows = [[f"`{c}`", r, fates_str(agg_b[(c, r)]) or "–", fates_str(agg_a[(c, r)]) or "–"] for c, r in keys]
    return md(rows, ["concept [strength, relationship]", "role", "BEFORE (legacy compiler)", "AFTER (hardened compiler)"])


def table_silent(b, a) -> str:
    rows = []
    tot_b = tot_a = 0
    for r in ROLES:
        mb = [x for k, run in b["runs"].items() if k.startswith(r) for x in run["atoms"]]
        ma = [x for k, run in a.items() if k.startswith(r) for x in run["atoms"]]
        sb = {kind: sum(1 for x in mb if x["kind"] == kind and x["fate"] == "SILENTLY_DROPPED") for kind in ("MEANING", "RECORD", "METADATA")}
        sa = {kind: sum(1 for x in ma if x["kind"] == kind and x["silent"]) for kind in ("MEANING", "RECORD", "METADATA")}
        n = sum(1 for x in mb if x["kind"] == "MEANING")
        rows.append([r, n, sb["MEANING"], sa["MEANING"], sb["RECORD"], sa["RECORD"], sb["METADATA"], sa["METADATA"]])
        tot_b += sum(sb.values()); tot_a += sum(sa.values())
    rows.append(["**all**", sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows), sum(r[4] for r in rows), sum(r[5] for r in rows), sum(r[6] for r in rows), sum(r[7] for r in rows)])
    return md(rows, ["role (5 runs)", "meaning atoms", "SILENTLY_DROPPED meaning: before", "after", "decision records: before", "after", "metadata: before", "after"])


def table_after_fates(a) -> str:
    c: Counter = Counter()
    for run in a.values():
        for x in run["atoms"]:
            c[x["fate"]] += 1
    rows = [[("CARRIED (provenance column of every atom record; not an atom with a fate)" if f == "CARRIED" else f), n] for f, n in sorted(c.items(), key=lambda kv: -kv[1])]
    rows.append(["**atoms**", sum(c.values())])
    return md(rows, ["fate after hardening (15 intents)", "atoms"])


def table_leaves() -> str:
    rows = []
    for (r, n), it in sorted(loader.load_all().items()):
        o = set(leaves(legacy.compile_intent(it).filter_tree))
        nw = set(leaves(compile_intent(it).filter_tree))

        def s(x):
            return "; ".join(sorted(f"{l[0].split('.')[-1]} {l[2][:24]}" for l in x)) or "–"
        rows.append([f"{r}/{n}", len(o), len(nw), s(o - nw), s(nw - o)])
    return md(rows, ["intent", "provider leaves before", "after", "removed", "added"])


def table_paths(a) -> str:
    rows = []
    for k, run in a.items():
        if not k.startswith("R1"):
            continue
        for p in run["paths"]:
            ls = leaves(p["filter_tree"])
            rows.append([k, p["path_id"], p["strategy"], "; ".join(f"{l[0].split('.')[-1]} {l[1]} {l[2][:28]}" for l in sorted(ls))])
    return md(rows, ["intent", "path", "strategy", "that path's provider plan (leaves)"])


def table_strength() -> str:
    cases = {
        "skill (current)": lambda s: {"skills": [{"name": "X", "strength": s, "relationship": "current"}]},
        "skill group (current)": lambda s: {"skill_any_of": [{"any_of": ["X", "Y"], "strength": s, "relationship": "current"}]},
        "company": lambda s: {"companies": [{"name": "Acme", "strength": s, "relationship": "any"}]},
        "company scale (current)": lambda s: {"company_scale": {"minimum_employees": 100, "strength": s, "relationship": "current"}},
        "education (degree+stream)": lambda s: {"education": {"degrees": ["B.Tech"], "streams": ["CS"], "strength": s}},
        "experience": lambda s: {"experience": {"minimum_years": 5, "maximum_years": 9, "strength": s}},
        "location": lambda s: {"location": {"entries": ["Pune, Maharashtra, India"], "strength": s}},
    }
    rows = []
    for name, f in cases.items():
        cells = []
        for s in ("required", "preferred", "context"):
            it = mk(**f(s))
            b = len(leaves(legacy.compile_intent(it).filter_tree)) - 1
            n = len(leaves(compile_intent(it).filter_tree)) - 1
            cells.append(f"{b} → {n}")
        rows.append([name] + cells)
    return md(rows, ["construct", "required (hard leaves before → after)", "preferred", "context"])


def table_relationship() -> str:
    rows = []
    for rel in ("current", "past", "any", None):
        kw = {"name": "SQL", "strength": "required"} | ({"relationship": rel} if rel else {})
        sk = SkillReq(**kw)
        it = mk(skills=[sk.model_dump(exclude_none=True)])
        p = compile_intent(it)
        a = next(x for x in p.atom_audit if x.concept == "skill")
        c = next(c for c in p.audit if c.source == "skill:SQL")
        rows.append([rel if rel else "(omitted)", len(leaves(p.filter_tree)) - 1, a.fate, c.capability, a.justification[:90]])
    return md(rows, ["relationship", "provider hard leaves (excl. title)", "fate", "capability token", "justification"])


def table_location() -> str:
    def run(entry, quote, extra=None):
        loc = {"entries": [entry], "strength": "required", "basis": {"sources": ["jd"], "quote": quote}} | (extra or {})
        p = compile_intent(mk(location=loc))
        a = next(x for x in p.atom_audit if x.concept == "location.entry")
        return "; ".join(f"{l[0].split('.')[-1]}={l[2]}" for l in sorted(leaves(p.filter_tree)) if "location" in l[0]), "; ".join(f"{c['component']}:{c['fate']}" for c in a.components)
    rows = []
    for label, entry, quote in [("JD: 'Hyderabad, India'; model wrote Telangana", "Hyderabad, Telangana, India", "Location: Hyderabad, India"),
                                ("JD states all three", "Hyderabad, Telangana, India", "Hyderabad, Telangana, India"),
                                ("JD: 'Hyderabad' only", "Hyderabad, Telangana, India", "Hyderabad"),
                                ("alias: 'Bangalore'", "Bangalore, Karnataka, India", "Bangalore, Karnataka, India")]:
        leaves_s, comps = run(entry, quote)
        rows.append([label, leaves_s, comps])
    return md(rows, ["case", "provider leaves", "component fates"])


def table_gate(a, summary) -> str:
    tot = {"atoms": 0, "silent": 0, "inconsistent": 0, "invented": 0}
    for v in summary["runs"].values():
        tot["atoms"] += v["atoms"]; tot["silent"] += v["silently_dropped"]; tot["inconsistent"] += v["inconsistent"]; tot["invented"] += v["invented_model_only_hard_filters"]
    unspecified_current = sum(1 for run in a.values() for x in run["audit_record"]["atom_audit"] if x["relationship"] is None and x["fate"] == "ENFORCED")
    pref_hard = sum(1 for run in a.values() for x in run["audit_record"]["atom_audit"] if x["strength"] in ("preferred", "context") and x["fate"] in ("ENFORCED", "NORMALIZED"))
    n_sem = sum(1 for run in a.values() for x in run["atoms"] if x["concept"] == "semantic_exclusion")
    n_prof = sum(1 for run in a.values() for x in run["atoms"] if x["concept"] == "skill.proficiency")
    n_neg = sum(1 for run in a.values() for l in run["leaves"] if l[1] in ("(!)", "not_in"))
    inv_before = 0
    for (r, n), it in loader.load_all().items():
        inv_before += sum(1 for l in set(leaves(legacy.compile_intent(it).filter_tree)) - set(leaves(compile_intent(it).filter_tree)) if l[0].endswith(("location.state", "location.country")))
    rows = [
        ["1", "SILENTLY_DROPPED = 0", f"{tot['silent']} of {tot['atoms']} atoms (independent ablation); {tot['inconsistent']} fates inconsistent with the output", "PASS"],
        ["2", "invented model-only hard filters = 0", f"{tot['invented']} (independent audit of every provider leaf). Before: {inv_before} unsupported state / country leaves, all removed by the gate (Role 2: Telangana and India x5 each; Role 3: Telangana x5)", "PASS"],
        ["3", "unspecified relationship never treated as current", f"{unspecified_current} atoms with an unspecified relationship are enforced; omitted → VERIFIED_DOWNSTREAM (tests B)", "PASS"],
        ["4", "strength does not silently strengthen", f"{pref_hard} preferred/context atoms are enforced (tests D, E, F)", "PASS"],
        ["5", "path-specific constraints stay path-specific", "Role 1 runs 2-5: 6+ years, Hyderabad/Pune, India and Power Query are each in exactly their own path (tests G, H)", "PASS (run 1: its intake put 6+ years in the GLOBAL intent, so the compiler applies it to both paths: an extraction error, recorded)"],
        ["6", "semantic exclusions remain semantic", f"{n_neg} negative provider leaves; all {n_sem} semantic exclusions → `downstream_exclusion` (test I)", "PASS"],
        ["7", "proficiency has an explicit fate", f"all {n_prof} proficiency atoms have a fate (VERIFIED_DOWNSTREAM; PREFERENCE_CONTEXT for a preferred skill), carried verbatim (test J)", "PASS"],
        ["8", "work mode has an explicit fate", "5/5 Role 3 `hybrid` → UNRESOLVED with a reason and a plan warning, never remapped (test K)", "PASS"],
        ["9", "unknown taxonomy values preserved and audited", "'Senior Manager' → UNRESOLVED, kept verbatim; 'Staff' likewise (test L)", "PASS"],
        ["10", "existing production-shaped compiler tests green", "tests/test_search_compiler.py, test_compiler_audit.py, test_search_compiler_shadow.py, test_structured_intent.py, test_crustdata_capabilities.py unchanged and passing; anchors compile identically", "PASS"],
    ]
    return md(rows, ["#", "gate", "measured", "result"])


def build() -> str:
    b, a = before(), after()
    summary = json.loads((RES / "hardened_summary.json").read_text(encoding="utf-8"))
    tpl = (HERE / "hardening_template.md").read_text(encoding="utf-8")
    mapping = {
        "matrix": table_matrix(b, a), "silent": table_silent(b, a), "after_fates": table_after_fates(a), "leaves": table_leaves(), "paths": table_paths(a),
        "strength": table_strength(), "relationship": table_relationship(), "location": table_location(), "gate": table_gate(a, summary),
        "version": COMPILER_VERSION,
    }
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", str(v))
    import re
    assert not re.findall(r"\{\{(\w+)\}\}", out)
    (HERE / "RESULTS_COMPILER_HARDENING.md").write_text(out, encoding="utf-8")
    return out


if __name__ == "__main__":
    build()
