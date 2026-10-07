"""Replay the post-Role-2 generic validators over the STORED Role 1 (v3) and Role 2 intents (EXPERIMENT ONLY; offline, no model call).

    python -m backend.experiments.intake_strategy.replay_cross_role_validators

Read-only over `results/`: it never rewrites a Role 1 or Role 2 file. Its purpose is to show (a) that each check detects the Role 2 error it
was added for and (b) what it does to Role 1, whose frozen verdicts are NOT changed by these checks (they use `validators.validate`).
Writes `results/cross_role_validator_replay.json`.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from backend.experiments.intake_strategy.experimental_schema import ExperimentalHiringIntent
from backend.experiments.intake_strategy.validators_cross_role import CROSS_ROLE_ERROR_CODES, validate_cross_role

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"


def replay(directory: Path, pattern: str, jd: str, brief: str) -> List[Dict[str, Any]]:
    out = []
    for path in sorted(directory.glob(pattern)):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not record.get("intent"):
            continue
        intent = ExperimentalHiringIntent.model_validate(record["intent"])
        report = validate_cross_role(intent, jd, brief)
        out.append({"file": path.name, "cross_role_errors": report["cross_role_errors"],
                    "examples": [d for d in report["diagnostics"] if d["code"] in CROSS_ROLE_ERROR_CODES][:6]})
    return out


def main() -> int:
    inputs = ROOT / "inputs"
    result = {
        "role1_v3": replay(RESULTS / "experimental_v3", "experimental_run*.json", (inputs / "role1_jd.txt").read_text(encoding="utf-8"),
                           (inputs / "role1_recruiter_brief.txt").read_text(encoding="utf-8")),
        "role2": replay(RESULTS / "role2", "role2_run*.json", (inputs / "role2_jd.txt").read_text(encoding="utf-8"),
                        (inputs / "role2_recruiter_brief.txt").read_text(encoding="utf-8")),
    }
    for arm, runs in result.items():
        total = Counter()
        for r in runs:
            total.update(r["cross_role_errors"])
        print(arm, "runs", len(runs), "per-run:", [r["cross_role_errors"] for r in runs])
        print("   totals:", dict(total))
    (RESULTS / "cross_role_validator_replay.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
