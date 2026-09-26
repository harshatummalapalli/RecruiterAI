"""Release 4 pre-deploy gate: ONE real-model smoke test of the intake path.

    python -m backend.experiments.intake_smoke

Real OpenAI (gpt-4o-mini, temperature 0) through the real IntakeReasoner, IntakeSessionManager, backstops, boundary and
confirmation gate. No scripted client. Four cases; exits non-zero if any check fails. Costs a few cents.
"""

import copy
import dataclasses
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List

from backend.models.intake import SearchBoundary
from backend.services.confirmation import gate_reasons
from backend.services.intake_reasoning import IntakeReasoner
from backend.services.intake_session import IntakeSessionManager
from backend.services.search_store import SearchStore

OUT = Path(__file__).resolve().parents[2] / "output" / "experiments" / "release4_smoke"
TORONTO_HYBRID = SearchBoundary(hiring_company="Northwind Payments", country="Canada", work_mode="hybrid", state="Ontario", city="Toronto", radius_miles=25.0)

CLEAR_JD = """AI Engineer
Northwind Payments builds fraud detection and dispute resolution for card issuers. Toronto.
About 70% of your time is backend engineering (Python, FastAPI, Kafka, PostgreSQL) and about 30% is applying ML and LLMs to fraud detection.
Required: 5+ years of professional software engineering experience. Strong Python. Experience with event-driven systems.
Nice to have: Snowflake, dbt."""

CONFLICT_JD = """AI Engineer
Northwind Payments builds fraud detection and dispute resolution for card issuers. Toronto.
About 70% of your time is backend engineering (Python, FastAPI, Kafka, PostgreSQL) and about 30% is applying ML and LLMs to fraud detection.
We are looking for an engineer with 3+ years of experience.
Requirements: 8-10 years of professional software engineering experience. Strong Python. Experience with event-driven systems.
Nice to have: Snowflake, dbt."""

CONTRADICTION_JD = """Product Analyst
Northwind Payments is hiring a Product Analyst in Toronto.
This is an entry-level role, but we need someone with 10+ years of experience in product analytics.
You will build dashboards in SQL and Tableau and partner with product managers.
Nice to have: Python."""

REMOTE_JD = """AI Engineer
Northwind Payments builds fraud detection and dispute resolution for card issuers.
This is a fully remote role.
About 70% of your time is backend engineering (Python, FastAPI, Kafka, PostgreSQL) and about 30% is applying ML and LLMs to fraud detection.
Required: 5+ years of professional software engineering experience. Strong Python. Experience with event-driven systems.
Nice to have: Snowflake, dbt."""

results: List[Dict[str, Any]] = []


def check(case: str, name: str, ok: bool, detail: str = "") -> bool:
    results.append({"case": case, "check": name, "pass": bool(ok), "detail": detail})
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return bool(ok)


def asks(record) -> List[Any]:
    return [i for i in record.result.decision.issues if i.decision == "ask"]


def describe(record) -> Dict[str, Any]:
    r = record.result
    return {
        "status": r.status,
        "asks": [{"issue": i.issue, "question": i.question, "options": [o["label"] for o in i.options], "backstop": i.backstop_category} for i in asks(record)],
        "tells": [i.insight_text for i in r.decision.issues if i.decision == "tell"],
        "limitations": r.decision.limitations,
        "warnings": r.decision.warnings,
        "identity": r.role_understanding.primary_candidate_identity.value,
        "posted_title": [r.role_understanding.posted_title, r.role_understanding.posted_title_source],
        "experience": [r.role_understanding.explicit_constraints.experience_minimum_years, r.role_understanding.explicit_constraints.experience_maximum_years],
        "core": r.decision.final_search_intent.hard_requirements,
        "supporting": r.decision.final_search_intent.strong_signals,
        "preferred": r.decision.final_search_intent.preferred_differentiators,
        "stated_in_jd": sorted(r.decision.final_search_intent.evidence),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="r4_smoke_"))
    store = SearchStore(storage_dir=workdir / "sessions")
    manager = IntakeSessionManager(reasoner=IntakeReasoner(), store=store)  # the REAL reasoner: real OpenAI
    log: Dict[str, Any] = {}

    # ---- 1. Clear role: zero questions, ready ------------------------------------------------------------------
    print("\nCASE 1 clear AI Engineer role")
    one = manager.start(CLEAR_JD, boundary=TORONTO_HYBRID, posted_title="AI Engineer")
    log["1"] = describe(one)
    check("1", "zero clarification questions", len(asks(one)) == 0, f"asks={[i.question for i in asks(one)]}")
    check("1", "status is ready", one.result.status == "ready")
    check("1", "confirmation gate is open", gate_reasons(one) == [], str(gate_reasons(one)))
    check("1", "posted title kept verbatim from the recruiter", one.result.role_understanding.posted_title == "AI Engineer" and one.result.role_understanding.posted_title_source == "recruiter")

    # ---- 2. Conflicting experience: exactly one question, answer, no reappearance, no drift, survives reload ----
    print("\nCASE 2 '3+ years' vs '8-10 years'")
    two = manager.start(CONFLICT_JD, boundary=TORONTO_HYBRID, posted_title="AI Engineer")
    log["2_before"] = describe(two)
    two_asks = asks(two)
    check("2", "exactly one question", len(two_asks) == 1, f"asks={[i.question for i in two_asks]}")
    material = bool(two_asks) and bool(re.search(r"experience|years|range", f"{two_asks[0].issue} {two_asks[0].question}", re.I))
    check("2", "the question is the material experience question", material, two_asks[0].question if two_asks else "")
    check("2", "blocked until answered", two.result.status == "needs_clarification" and gate_reasons(two) != [])
    if two_asks:
        before = copy.deepcopy(dataclasses.asdict(two.result))
        option = next((o for o in two_asks[0].options if re.search(r"8", o["label"] + o["value"])), two_asks[0].options[-1])
        answered = manager.answer(two.session_id, two_asks[0].id, option["value"], option["label"])
        after = dataclasses.asdict(answered.result)
        log["2_after"] = describe(answered)
        log["2_chosen_option"] = option
        check("2", "the question does not reappear", not any(re.search(r"experience|years|range", f"{i.issue} {i.question}", re.I) for i in asks(answered)), str([i.question for i in asks(answered)]))
        check("2", "ready after the answer", answered.result.status == "ready" and gate_reasons(answered) == [], str(gate_reasons(answered)))

        # Unrelated interpretation must not drift: only fields the answer named may differ.
        changed = {c.field for c in answered.result.confirmed}
        allowed_role = {"experience": {"explicit_constraints"}, "seniority": {"seniority_scope"}, "identity": {"primary_candidate_identity"}, "leadership": {"leadership_type"}}
        allowed = set().union(*(allowed_role[f] for f in changed if f in allowed_role)) if changed else set()
        drifted = [k for k in before["role_understanding"] if before["role_understanding"][k] != after["role_understanding"][k] and k not in allowed]
        check("2", "no unrelated role interpretation drift", not drifted, f"drifted={drifted} allowed={sorted(allowed)} confirmed={sorted(changed)}")
        b_c, a_c = before["role_understanding"]["explicit_constraints"], after["role_understanding"]["explicit_constraints"]
        other_constraints = [k for k in b_c if b_c[k] != a_c[k] and k not in ("experience_minimum_years", "experience_maximum_years")]
        check("2", "no unrelated constraint drift", not other_constraints, str(other_constraints))
        recorded = {c.item for c in answered.result.confirmed if c.field == "requirement"}
        b_f, a_f = before["decision"]["final_search_intent"], after["decision"]["final_search_intent"]
        generic_years = re.compile(r"^\W*\d+\s*\+?\s*(?:-\s*\d+\s*)?(?:years?|yrs?)\b", re.I)
        req_drift = []
        for tier in ("hard_requirements", "strong_signals", "preferred_differentiators"):
            removed = [x for x in b_f[tier] if x not in a_f[tier]]
            added = [x for x in a_f[tier] if x not in b_f[tier]]
            req_drift += [f"{tier} removed {x!r}" for x in removed if not generic_years.search(x) and x not in recorded]
            req_drift += [f"{tier} added {x!r}" for x in added if x not in recorded]
        check("2", "no unrelated requirement drift (only years sentences or recorded moves changed)", not req_drift, str(req_drift))
        wanted = tuple(int(n) for n in re.findall(r"\d+", option["label"])[:2])
        check("2", "the experience range now matches the answer chosen", (a_c["experience_minimum_years"], a_c["experience_maximum_years"]) == wanted, f"{b_c['experience_minimum_years']}-{b_c['experience_maximum_years']} -> {a_c['experience_minimum_years']}-{a_c['experience_maximum_years']} (chose {option['label']!r})")
        check("2", "the answer is recorded as confirmed by the recruiter", any(c.field == "experience" for c in answered.result.confirmed), str([c.description for c in answered.result.confirmed]))

        # Reload: a brand-new manager reading only the stored session.
        fresh = IntakeSessionManager(store=SearchStore(storage_dir=workdir / "sessions"))
        reloaded = fresh.get(two.session_id)
        check("2", "reload returns exactly the same brief", dataclasses.asdict(reloaded.result) == after)
        check("2", "the confirmed answer survives reload", [c.description for c in reloaded.result.confirmed] == [c.description for c in answered.result.confirmed] and len(reloaded.answers) == 1)
        check("2", "no question reappears after reload", not asks(reloaded))

    # ---- 3. Junior + senior: contradiction, blocked until resolved --------------------------------------------
    print("\nCASE 3 Product Analyst: entry-level vs 10+ years")
    three = manager.start(CONTRADICTION_JD, boundary=TORONTO_HYBRID)
    log["3_before"] = describe(three)
    contradiction = [i for i in asks(three) if i.backstop_category == "experience_seniority" or re.search(r"seniority|entry|junior|senior|years", f"{i.issue} {i.question}", re.I)]
    check("3", "the contradiction is raised", bool(contradiction), str([i.question for i in asks(three)]))
    check("3", "search is blocked", three.result.status == "needs_clarification" and bool(gate_reasons(three)), str(gate_reasons(three)))
    # A boundary edit must not unblock it.
    still = manager.update_boundary(three.session_id, dataclasses.replace(TORONTO_HYBRID, radius_miles=40.0))
    check("3", "still blocked after an unrelated boundary edit", still.result.status == "needs_clarification" and bool(gate_reasons(still)))
    if contradiction:
        opt = next((o for o in contradiction[0].options if "senior" in o["label"].lower() or "stated" in o["value"]), contradiction[0].options[0])
        resolved = manager.answer(three.session_id, contradiction[0].id, opt["value"], opt["label"])
        log["3_after"] = describe(resolved)
        log["3_chosen_option"] = opt
        check("3", "resolving it clears the block", not [i for i in asks(resolved) if i.backstop_category == "experience_seniority"], str([i.question for i in asks(resolved)]))
        check("3", "the contradiction does not come back", not [i for i in manager.get(three.session_id).result.decision.issues if i.decision == "ask" and i.backstop_category == "experience_seniority"])

    # ---- 4. JD says remote, recruiter chose Hybrid -----------------------------------------------------------
    print("\nCASE 4 JD says remote, boundary says Hybrid")
    four = manager.start(REMOTE_JD, boundary=TORONTO_HYBRID, posted_title="AI Engineer")
    log["4"] = describe(four)
    work_mode_asks = [i for i in asks(four) if re.search(r"remote|onsite|on-site|hybrid|work mode|office", f"{i.issue} {i.question}", re.I)]
    check("4", "no work-mode question is asked", not work_mode_asks, str([i.question for i in work_mode_asks]))
    notice = [i for i in four.result.decision.issues if i.backstop_category == "work_mode_precedence"]
    jd_mode_recorded = (four.result.role_understanding.explicit_constraints.work_mode or "").lower()
    check("4", "the boundary precedence is visible as a TELL", bool(notice) and notice[0].decision == "tell", f"jd work_mode={jd_mode_recorded!r} notice={[n.insight_text for n in notice]}")
    check("4", "the work-mode limitation is shown", bool(four.result.decision.limitations) and "hybrid" in four.result.decision.limitations[0].lower(), str(four.result.decision.limitations))
    check("4", "it is not a blocking contradiction", not [i for i in asks(four) if i.backstop_category == "location_work_mode"] and not any("remote/anywhere" in w for w in four.result.decision.warnings))
    check("4", "the search is not blocked by work mode", not [r for r in gate_reasons(four) if re.search(r"work mode|remote", r, re.I)], str(gate_reasons(four)))

    (OUT / "results.json").write_text(json.dumps({"checks": results, "detail": log}, indent=1, default=str), encoding="utf-8")
    failed = [r for r in results if not r["pass"]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed. Detail: {OUT / 'results.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
