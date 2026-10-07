"""Load the frozen Role 1 / Role 2 / Role 3 experimental intents, read-only.

Nothing here calls a model, a provider or the network. The stored intents are parsed into `ExperimentalHiringIntent` and never written back."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent

ROOT = Path(__file__).resolve().parents[1] / "intake_strategy" / "results"
RAW_ROOT = Path(__file__).resolve().parents[3] / "output" / "experiments" / "intake_strategy"

# role -> (results directory, file pattern). Role 1 = the accepted Role 1 representation (prompt_v3); Role 2 = prompt_v3 (pre-`advanced`,
# pre-`work_mode`); Role 3 = prompt_v4.
ARMS: Dict[str, Tuple[str, str]] = {
    "R1": ("experimental_v3", "experimental_run{n}.json"),
    "R2": ("role2", "role2_run{n}.json"),
    "R3": ("role3", "role3_run{n}.json"),
}
RUNS = (1, 2, 3, 4, 5)


def path_of(role: str, n: int) -> Path:
    d, pat = ARMS[role]
    return ROOT / d / pat.format(n=n)


def load_intent(role: str, n: int) -> ExperimentalHiringIntent:
    data = json.loads(path_of(role, n).read_text(encoding="utf-8"))
    if data.get("error"):
        raise ValueError(f"{role} run {n} has no intent ({data['error']})")
    return ExperimentalHiringIntent.model_validate(data["intent"])


def load_all() -> Dict[Tuple[str, int], ExperimentalHiringIntent]:
    return {(r, n): load_intent(r, n) for r in ARMS for n in RUNS}


def source_hashes() -> Dict[str, str]:
    """sha256 of each stored run file (the evidence base), so the baseline says exactly which bytes it compiled."""
    return {f"{r}/{n}": hashlib.sha256(path_of(r, n).read_bytes()).hexdigest() for r in ARMS for n in RUNS}


def relationship_omission_in_raw_output() -> Dict[str, Any]:
    """How often the model actually OMITTED `relationship` on a skill / group / company in its raw JSON. Uses the gitignored raw outputs when they
    are present in this checkout; returns {'available': False} otherwise (the committed baseline records the count it saw)."""
    out: Dict[str, Any] = {"available": False}
    if not RAW_ROOT.exists():
        return out
    per_role: Dict[str, Dict[str, int]] = {}
    for role, (d, pat) in ARMS.items():
        atoms = omitted = 0
        for n in RUNS:
            p = RAW_ROOT / d / pat.format(n=n)
            if not p.exists():
                return {"available": False}
            run = json.loads(p.read_text(encoding="utf-8"))
            raw = json.loads(run["model_calls"][-1]["raw_text"])
            for key in ("skills", "skill_any_of", "companies"):
                for item in raw.get(key) or []:
                    atoms += 1
                    omitted += "relationship" not in item
            cs = raw.get("company_scale")
            if cs:
                atoms += 1
                omitted += "relationship" not in cs
        per_role[role] = {"atoms": atoms, "relationship_omitted_in_raw_output": omitted}
    return {"available": True, "per_role": per_role}
