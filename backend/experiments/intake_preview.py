"""Build saved intake fixtures for the local Living Brief preview. No network, no OpenAI, no CrustData.

    python -m backend.experiments.intake_preview

It runs the REAL intake code (session manager, backstops, boundary, pinned answers, translator) against canned model
output, and writes frontend/src/preview-data/intake-<state>.json (git-ignored). Then:

    cd frontend && npm run dev   ->   http://localhost:5173/preview-brief.html

Each fixture is exactly what the API returns for that state, so the preview shows the real screens on real shapes.
"""

import copy
import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.models.intake import SearchBoundary
from backend.services.intake_reasoning import IntakeReasoner
from backend.services.intake_session import IntakeSessionManager
from backend.services.search_store import SearchStore
from backend.services.search_translator import build_confirmed_hiring_intent, to_search_intent

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "preview-data"

RAW = """AI Engineer
Northwind Payments builds fraud detection and dispute resolution for card issuers.
About 70% of your time is backend engineering (Python, FastAPI, Kafka, PostgreSQL) and about 30% is applying ML and LLMs to fraud detection.
We are looking for an engineer with 3+ years of experience. Requirements: 8-10 years of professional software engineering experience. Strong Python. Experience with event-driven systems.
Nice to have: Snowflake, dbt."""

TORONTO = SearchBoundary(hiring_company="Northwind Payments", country="Canada", work_mode="hybrid", state="Ontario", city="Toronto", radius_miles=25.0)
REMOTE = SearchBoundary(hiring_company="Northwind Payments", country="Canada", work_mode="remote", remote_scope="anywhere")

TASK_A: Dict[str, Any] = {
    "posted_title": "AI Engineer",
    "primary_candidate_identity": {"value": "Backend-heavy AI Engineer", "evidence": "About 70% of your time is backend engineering", "source": "inferred"},
    "hiring_company": {"value": "Northwind Payments", "evidence": "Northwind Payments builds fraud detection", "source": "explicit"},
    "candidate_archetype": {"value": "An experienced backend engineer who has applied ML in production.", "source": "inferred"},
    "role_interpretation": {
        "value": "This is primarily a backend engineering role that applies machine learning to fraud detection. Even though the title says AI Engineer, the JD says about 70% of the work is backend engineering in Python, FastAPI and Kafka, with ML as the smaller share.",
        "evidence": "About 70% of your time is backend engineering",
        "source": "inferred",
    },
    "seniority_scope": {"value": "Senior", "evidence": "8-10 years of professional software engineering experience", "source": "inferred"},
    "leadership_type": {"value": "none", "evidence": "no leadership mentioned"},
    "core_capabilities": [{"value": "Python backend services", "tier_signal": "required", "evidence": "Strong Python."}],
    "supporting_capabilities": [],
    "differentiators": [],
    "technologies_mentioned": [
        {"category": "Languages and frameworks", "items": ["Python", "FastAPI"]},
        {"category": "Data and messaging", "items": ["Kafka", "PostgreSQL", "Snowflake", "dbt"]},
    ],
    "domain": ["Payments", "Fraud detection"],
    "explicit_constraints": {
        "locations": [{"city": "Toronto", "state": "Ontario", "country": "Canada"}],
        "work_mode": "hybrid",
        "experience_minimum_years": 3,
        "experience_maximum_years": 10,
        "employment_type": None,
        "exclusions": [],
    },
    "open_questions_the_text_leaves_genuinely_unresolved": [],
}

EXPERIENCE_ASK = {
    "issue": "Conflicting experience ranges",
    "decision": "ask",
    "reasoning": "The description states two different ranges.",
    "question": "The description states 3+ years and also 8-10 years. Which range is correct?",
    "options": [{"value": "3plus", "label": "3+ years"}, {"value": "8to10", "label": "8-10 years"}],
    "consequence_if_answer_a": "Sets the experience filter to 3+ years.",
    "consequence_if_answer_b": "Sets the experience filter to 8-10 years.",
}
TELL = {
    "issue": "Title versus work",
    "decision": "tell",
    "reasoning": "The work is clear.",
    "insight_text": "Even though the title says AI Engineer, about 70% of the work is backend engineering, so backend titles are searched too.",
}
TASK_B: Dict[str, Any] = {
    "issues": [EXPERIENCE_ASK, TELL],
    "recommended_ask_count": 1,
    "stop_reasoning": "Nothing else changes what would be searched.",
    "warnings": [],
    "search_consequence_summary": "Backend Engineer and Software Engineer titles are searched alongside AI Engineer, because most of the work is backend.",
    "final_search_intent": {
        "hard_requirements": ["3+ years of professional experience", "Python backend services", "Event-driven systems", "PostgreSQL"],
        "strong_signals": ["FastAPI", "Kafka"],
        "preferred_differentiators": ["Snowflake", "dbt"],
        "natural_language_search_query": "Senior backend engineer with Python and event-driven systems experience.",
        "exclusions": [],
    },
}
PATCH_YEARS = {
    "reasoning": "You chose 8-10 years.",
    "changes": [{"op": "set_experience", "minimum_years": 8, "maximum_years": 10}],
    "natural_language_search_query": "Senior backend engineer with 8-10 years of Python and event-driven systems experience.",
    "new_issues": [],
}


class _Reply:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.output_text = json.dumps(payload)


class _Canned:
    """Returns queued payloads in order, like a model would."""

    def __init__(self, payloads: List[Dict[str, Any]]) -> None:
        self._payloads = [copy.deepcopy(p) for p in payloads]
        self.responses = self

    def create(self, **_: Any) -> _Reply:
        return _Reply(self._payloads.pop(0))


def _manager(payloads: List[Dict[str, Any]], directory: Path) -> IntakeSessionManager:
    return IntakeSessionManager(reasoner=IntakeReasoner(client=_Canned(payloads)), store=SearchStore(storage_dir=directory))


def _fixture(name: str, record: Any, next_state: Optional[str] = None) -> Dict[str, Any]:
    intent = None
    if record.result.status == "ready" and record.boundary is not None:
        intent = dataclasses.asdict(to_search_intent(build_confirmed_hiring_intent(record.result, boundary=record.boundary)))
    return {
        "name": name,
        "next": next_state,
        "session_id": record.session_id,
        "result": dataclasses.asdict(record.result),
        "boundary": dataclasses.asdict(record.boundary),
        "posted_title_input": record.posted_title_input,
        "intent": intent,
    }


def main() -> None:
    import os

    os.environ.setdefault("OPENAI_API_KEY", "preview-not-used")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("intake-*.json"):
        old.unlink()
    workdir = Path(tempfile.mkdtemp(prefix="intake_preview_"))
    fixtures: List[Dict[str, Any]] = []

    # 1. Draft: one open question. Answering it (one small call, everything else pinned) leads to 2.
    manager = _manager([TASK_A, TASK_B, PATCH_YEARS], workdir / "a")
    started = manager.start(RAW, boundary=TORONTO, posted_title="AI Engineer")
    fixtures.append(_fixture("1 Draft: a question to answer", started, "2 Ready: after the answer"))
    ask_id = next(i.id for i in started.result.decision.issues if i.decision == "ask")
    answered = manager.answer(started.session_id, ask_id, "8to10", "8-10 years")
    fixtures.append(_fixture("2 Ready: after the answer", answered))

    # 3. A contradiction the deterministic backstop found.
    contradiction_raw = "Product Analyst\nEntry-level role, but we need 10+ years of experience with SQL and dashboards.\nNice to have: Tableau."
    task_a = dict(TASK_A, posted_title="Product Analyst", role_interpretation={"value": "An analyst role focused on SQL and dashboards.", "evidence": "SQL and dashboards", "source": "explicit"}, primary_candidate_identity={"value": "Product Analyst", "evidence": "Product Analyst", "source": "explicit"}, seniority_scope={"value": "Entry level", "evidence": "Entry-level role", "source": "explicit"})
    task_b = dict(TASK_B, issues=[], recommended_ask_count=0, search_consequence_summary=None, final_search_intent={"hard_requirements": ["10+ years of experience with SQL and dashboards"], "strong_signals": [], "preferred_differentiators": ["Tableau"], "natural_language_search_query": "Entry-level product analyst with SQL.", "exclusions": []})
    started = _manager([task_a, task_b], workdir / "c").start(contradiction_raw, boundary=TORONTO)
    fixtures.append(_fixture("3 Draft: a contradiction to resolve", started))

    # 4. A clear role: zero questions.
    clear_b = dict(TASK_B, issues=[TELL], recommended_ask_count=0)
    clear_b["final_search_intent"] = dict(TASK_B["final_search_intent"], hard_requirements=["Python backend services", "Event-driven systems", "PostgreSQL"])
    started = _manager([TASK_A, clear_b], workdir / "d").start(RAW.replace("We are looking for an engineer with 3+ years of experience. ", ""), boundary=TORONTO, posted_title="AI Engineer")
    fixtures.append(_fixture("4 Ready: a clear role, no questions", started))

    # 5. Remote anywhere in the country, ready.
    started = _manager([TASK_A, clear_b], workdir / "e").start(RAW, boundary=REMOTE, posted_title="AI Engineer")
    fixtures.append(_fixture("5 Ready: remote, anywhere in Canada", started))

    # 6. No core requirements identified: advisory, does not block.
    zero_b = dict(clear_b, final_search_intent=dict(clear_b["final_search_intent"], hard_requirements=[]))
    started = _manager([TASK_A, zero_b], workdir / "f").start(RAW, boundary=TORONTO, posted_title="AI Engineer")
    fixtures.append(_fixture("6 Ready: no core requirements", started))

    # 7. The description names a different country than the boundary.
    task_a_us = copy.deepcopy(TASK_A)
    task_a_us["explicit_constraints"]["locations"] = [{"city": "Austin", "state": "Texas", "country": "United States"}]
    started = _manager([task_a_us, clear_b], workdir / "g").start(RAW, boundary=TORONTO, posted_title="AI Engineer")
    fixtures.append(_fixture("7 Draft: description and boundary disagree", started))

    # 8. No title typed: the title read from the description (verified to appear in it).
    started = _manager([TASK_A, clear_b], workdir / "h").start(RAW, boundary=TORONTO)
    fixtures.append(_fixture("8 Ready: title read from the description", started))

    for index, fixture in enumerate(fixtures, start=1):
        (OUT / f"intake-{index}.json").write_text(json.dumps(fixture, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Wrote {len(fixtures)} intake fixtures to {OUT}")
    print("Now run: cd frontend && npm run dev  ->  http://localhost:5173/preview-brief.html")


if __name__ == "__main__":
    main()
