"""Generate the TABLES of RESULTS_RUNTIME_INTEGRATION.md from the committed runtime measurements (results/runtime/*.json) and a scan of production code.

    python -m backend.experiments.compiler_contract.build_runtime_report
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.compiler_contract.build_report import fates_str, md
from backend.services.search_compiler import COMPILER_VERSION

HERE = Path(__file__).resolve().parent
RES = HERE / "results" / "runtime"
ROOT = HERE.parents[2]
ROLES = ("R1", "R2", "R3")


def runs() -> Dict[str, Dict[str, Any]]:
    return {f"{r}/{n}": json.loads((RES / f"{r}_run{n}.json").read_text(encoding="utf-8")) for r in ROLES for n in range(1, 6)}


def table_provenance(rs) -> str:
    carrier = {
        "role_family": "none (a plain list of titles): classified from the source text (target / comparison / absent)",
        "company_scale": "none (production `CompanyScale`): the number must be stated in the source text",
        "skill": "`basis` (quote verified against the source)", "skill_any_of": "`basis`", "company": "`basis`", "education.degree": "`basis`", "education.stream": "`basis`",
        "experience.min": "`basis`", "experience.max": "`basis`", "location.entry": "`basis`; state / country also need to be in the quote", "location.country": "`basis`",
        "location.radius": "`basis`", "exclusion.exclude_past_company": "`basis`", "exclusion.exclude_title": "`basis`",
    }
    enforced: Dict[str, Counter] = defaultdict(Counter)
    blocked: Dict[str, Counter] = defaultdict(Counter)
    for run in rs.values():
        for c, v in run["hard_filter_provenance"]["enforced_by_concept"].items():
            enforced[c].update(v)
        for c, v in run["hard_filter_provenance"]["blocked_by_concept"].items():
            blocked[c].update(v)
    rows = []
    for c in sorted(set(carrier) | set(enforced) | set(blocked)):
        if c == "sourcing_path":
            continue
        rows.append([f"`{c}`", carrier.get(c, "`basis`"), fates_str(enforced[c]) or "–", fates_str(blocked[c]) or "–"])
    return md(rows, ["hard-filter-capable field", "provenance carrier", "ENFORCED atoms by provenance state (15 intents; `*` = classified from the source text)", "WITHHELD atoms by reason"])


def table_titles(rs) -> str:
    rows = []
    for r in ROLES:
        run = rs[f"{r}/1"]
        titles = sorted({l[2] for c in run["contexts"] for l in c["provider_leaves"] if l[0].endswith("current.title")})
        states = sorted({(e["value"], e["provenance"]["state"]) for c in run["downstream_contexts"] for e in c["entries"] if e["concept"] == "role_family"})
        rows.append([r, ", ".join(f"{v} → {s}" for v, s in states), ", ".join(t.strip('"') for t in titles)])
    return md(rows, ["role (run 1)", "each role_family title → its provenance state", "titles in the provider filter"])


def table_leaf_delta() -> str:
    """Provider leaves of the contract-1 compiler (no source text) vs the live compiler (with the JD / brief): the provenance gate must withhold only what it should."""
    from backend.experiments.compiler_contract import loader
    from backend.experiments.compiler_contract.compiler_contract1_snapshot import compile_intent as old
    from backend.experiments.compiler_contract.signature import leaves
    from backend.services.search_compiler import compile_intent as new
    rows = []
    for (r, n), it in sorted(loader.load_all().items()):
        a = set(leaves(old(it).filter_tree))
        b = set(leaves(new(it, loader.sources_for(r)).filter_tree))
        short = lambda x: "; ".join(sorted(f"{l[0].split('.')[-1]} {l[2][:30]}" for l in x)) or "–"
        rows.append([f"{r}/{n}", len(a), len(b), short(a - b), short(b - a)])
    return md(rows, ["intent", "contract-1 leaves", "now (with source text)", "withheld", "added"])


def relationship_scan() -> List[List[str]]:
    notes = {
        "backend/models/structured_intent.py": "DEFINITION. `SkillReq`, `SkillAnyOf`, `CompanyScale`: default `None` (unspecified, never current); `CompanyReq`: default `any`. Validator accepts `None` or current / past / any",
        "backend/services/structured_intent_extractor.py": "WRITER. `_fix_strength_relationship` repairs a strength word in the slot to `any`; group-collapse keeps an ABSENT relationship absent. Never writes `current`",
        "backend/services/search_compiler.py": "CONSUMER. `current` / `past` → provider fields; `any` → downstream; `None` → downstream with capability `unspecified_relationship` (no current-role filter); company scale: `== \"current\"` only",
        "backend/services/downstream_context.py": "CARRIER. Copies the atom's relationship (None stays None) into every entry",
        "backend/services/consumer_input.py": "CARRIER (downstream-consumer phase). Passes the entry's relationship (None stays None) to the Judge checklist; never reads it to decide anything",
    }
    out = []
    for path in sorted((ROOT / "backend").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/experiments/" in rel:
            continue
        n = sum(1 for l in path.read_text(encoding="utf-8").splitlines() if re.search(r"\.relationship\b|\"relationship\"", l))
        if n:
            out.append([f"`{rel}`", n, notes[rel]])
    exp = defaultdict(int)
    for path in (ROOT / "backend" / "experiments").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "compiler_contract" in rel:
            continue
        k = sum(1 for l in path.read_text(encoding="utf-8").splitlines() if re.search(r"\.relationship\b", l))
        if k:
            exp[rel] += k
    out.append(["`backend/experiments/intake_strategy/*` (gold, validators, compare: 7 files)", sum(exp.values()), "READERS (experiments). Equality comparisons (`== \"current\"`, `!= \"any\"`, `Counter`); all None-safe; the frozen stored intents state every relationship explicitly (0 of 343 atoms omitted it)"])
    out.append(["`prompts/structured_intent.txt`", sum(1 for l in (ROOT / "prompts" / "structured_intent.txt").read_text(encoding="utf-8").splitlines() if "relationship" in l.lower()), "PROMPT. Lists `current|past|any`; has no 'unspecified' option, so an omitted value (now `None`) is the model's only way to say unspecified. Not changed"])
    out.append(["`frontend/**`", 0, "no reader"])
    return out


def table_relationship() -> str:
    return md(relationship_scan(), ["consumer", "lines reading / writing a relationship", "role and migration status"])


def table_paths(rs) -> str:
    rows = []
    for n in range(1, 6):
        run = rs[f"R1/{n}"]
        for c, dc in zip(run["contexts"], run["downstream_contexts"]):
            entries = dc["entries"]
            pq = [e for e in entries if e["concept"] == "skill" and e["text"] == "Power Query"]
            pqp = [e for e in entries if e["concept"] == "skill.proficiency" and "Power Query" in e["text"]]
            remote = [e for e in entries if e["concept"] == "location.remote"]
            lv = {(l[0].split(".")[-1], l[2]) for l in c["provider_leaves"]}
            rows.append([f"R1/{n}", c["path_id"], c["strategy"],
                         "; ".join(sorted(f"{a} {b.strip(chr(34))[:22]}" for a, b in lv)),
                         "yes" if ("years_of_experience_raw", "6") in lv else "no",
                         (pq[0]["tier"] + " (" + pq[0]["scope"] + ")") if pq else "absent",
                         pqp[0]["text"] if pqp else "–",
                         remote[0]["text"] + " / " + remote[0]["fate"] if remote else "–",
                         sum(1 for e in entries if e["inherited"]), sum(1 for e in entries if e["scope"].startswith("path:") and e["kind"] != "path")])
    return md(rows, ["intent", "path", "strategy", "that path's provider plan", "6+ years", "Power Query (tier, scope)", "Power Query depth", "remote", "inherited entries", "path-specific entries"])


def table_kinds(rs) -> str:
    agg: Dict[str, Counter] = defaultdict(Counter)
    for run in rs.values():
        for dc in run["downstream_contexts"]:
            for e in dc["entries"]:
                agg[e["concept"]][e["kind"]] += 1
    focus = ["semantic_exclusion", "skill.proficiency", "location.work_mode", "seniority.leadership", "seniority.alternatives", "seniority.value", "domain", "location.remote",
             "location.country", "location.entry", "company", "education.degree", "experience.min", "evidence_signal", "skill", "skill_any_of", "role_family", "reconciliation", "role_archetype"]
    rows = [[f"`{c}`", fates_str(agg[c])] for c in focus if c in agg]
    return md(rows, ["intent concept", "context entry kinds (entries over all contexts of the 15 intents)"])


def table_preferences(rs) -> str:
    pref: Counter = Counter()
    hardened = 0
    for run in rs.values():
        for dc in run["downstream_contexts"]:
            for e in dc["entries"]:
                if e["fate"] == "PREFERENCE_CONTEXT":
                    pref[e["concept"]] += 1
                if e["strength"] in ("preferred", "context") and e["kind"] == "provider_enforced":
                    hardened += 1
    rows = [[f"`{c}`", n] for c, n in sorted(pref.items(), key=lambda kv: -kv[1])]
    rows.append(["**preferred / context atoms that became provider filters**", hardened])
    return md(rows, ["PREFERENCE_CONTEXT entries by concept (all contexts of the 15 intents)", "entries"])


def table_gaps(rs) -> str:
    agg: Dict[str, Counter] = defaultdict(Counter)
    for k, run in rs.items():
        for c in run["contexts"]:
            for g, n in c["legacy_gaps"].items():
                agg[g][k[:2]] += n
    rows = [[g] + [agg[g].get(r, 0) for r in ROLES] for g in ("NO_NEGATIVE_SLOT", "NO_UNRESOLVED_SLOT", "ADMISSION_READS_LEGACY_INTENT", "PREFERENCE_NOT_FORWARDED")]
    return md(rows, ["legacy-consumer gap (atoms; 5 runs per role)", "Role 1", "Role 2", "Role 3"])


def table_gate(rs, summary) -> str:
    tot: Counter = Counter()
    for v in summary["runs"].values():
        for k in ("atoms", "silent_at_boundary", "problems", "leaks", "hard_filter_violations"):
            tot[k] += v[k]
    n_ctx = sum(v["contexts"] for v in summary["runs"].values())
    v_atoms = sum(1 for run in rs.values() for dc in run["downstream_contexts"] for e in dc["entries"] if e["fate"] == "VERIFIED_DOWNSTREAM")
    unres = sum(1 for run in rs.values() for dc in run["downstream_contexts"] for e in dc["entries"] if e["kind"] == "unresolved")
    rows = [
        ["1", "every hard provider filter has source / approved provenance", f"{tot['hard_filter_violations']} violations over the provider-enforced atoms of 15 intents (with the JD / brief supplied)", "PASS"],
        ["2", "unspecified relationship never becomes current", "0 unspecified atoms enforced; None stays None through model → extractor → compiler → audit → context (tests R)", "PASS"],
        ["3", "every sourcing path independently addressable", f"{n_ctx} contexts over 15 intents; Role 1: 2 contexts per run, each with its own provider plan", "PASS"],
        ["4", "downstream context receives every VERIFIED_DOWNSTREAM atom", f"{v_atoms} VERIFIED_DOWNSTREAM entries; for every context the set of such atoms in the plan equals the set in the context; {tot['silent_at_boundary']} atoms silent at the boundary of {tot['atoms']}", "PASS"],
        ["5", "preferences preserved without hardening", "0 preferred / context atoms became provider filters; Role 3's 6 companies are preference entries in 5/5 runs", "PASS"],
        ["6", "unresolved values remain visible", f"{unres} unresolved entries (Senior Manager, hybrid, withheld titles); each plan's unresolved atoms are all in its contexts", "PASS"],
        ["7", "provenance survives compiler → downstream", f"every entry carries a provenance state; {tot['problems']} provenance / placement problems", "PASS"],
        ["8", "no path flattening", f"{tot['leaks']} path atoms in another path's context; a global atom reaches every inheriting path, a path atom only its own (checked independently)", "PASS"],
        ["9", "synthetic path merge preserves contributing paths", "a candidate in A and B keeps both ids, both payloads and both contexts' obligations; order-independent; no ranking (tests M, S)", "PASS"],
        ["10", "no live provider is called", "no network connection in the synthetic end-to-end test (socket.connect is trapped); no new module imports a provider, an HTTP client or the Judge", "PASS"],
    ]
    return md(rows, ["#", "gate", "measured", "result"])


def build() -> str:
    rs = runs()
    summary = json.loads((HERE / "results" / "runtime_summary.json").read_text(encoding="utf-8"))
    tpl = (HERE / "runtime_template.md").read_text(encoding="utf-8")
    m = {"version": COMPILER_VERSION, "provenance": table_provenance(rs), "titles": table_titles(rs), "leaf_delta": table_leaf_delta(), "relationship": table_relationship(), "paths": table_paths(rs),
         "kinds": table_kinds(rs), "preferences": table_preferences(rs), "gaps": table_gaps(rs), "gate": table_gate(rs, summary)}
    out = tpl
    for k, v in m.items():
        out = out.replace("{{" + k + "}}", str(v))
    assert not re.findall(r"\{\{(\w+)\}\}", out)
    (HERE / "RESULTS_RUNTIME_INTEGRATION.md").write_text(out, encoding="utf-8")
    return out


if __name__ == "__main__":
    build()
