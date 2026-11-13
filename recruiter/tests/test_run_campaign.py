"""RUN — the paced, budget-capped campaign loop. Offline; a counting enricher
proves the round enriches only a budgeted batch and stops at budget / exhaustion."""

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("backend.services.search_store")

from backend.bridge.intake_service import IntakeService
from backend.bridge.session_store import ConfirmationStore
from backend.services.search_store import SearchStore
from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake import IntakeAgent, Understanding
from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory, LearnedCapability
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import ReadRequirement
from recruiter.agents.ranking import RankingAgent
from recruiter.agents.ranking.model import ScreenResult
from recruiter.agents.search import SearchAgent
from recruiter.candidates import CandidateRecord
from recruiter.pipeline import Pipeline

N = 25   # all Backend, so every reserve member matches the target


class _Provider:
    def count(self, query): return 999
    def search(self, query, page_size):
        return [CandidateRecord(f"be{i}", name=f"Backend {i}", title="Backend Engineer",
                                location="Pune, India", raw={"basic_profile": {"headline": "APIs"}},
                                matched_queries=("natural_language",)) for i in range(N)]


class _Judge:
    def judge(self, role, record):
        return tuple({"tier": r.tier, "signal_text": r.text, "quote": r.text, "verdict": "met"} for r in role.requirements)


class _KeepAll:
    def screen(self, role, records, feedback_context=None):
        return tuple(ScreenResult(keep=True, score=1.0) for _ in records)


class _CountingEnricher:
    def __init__(self): self.n = 0
    def enrich(self, record):
        record.enriched = True
        self.n += 1


def _reader(notes, posted_title=None):
    return Understanding(identity="Backend Engineer", posted_title="Backend Engineer", posted_title_source="jd",
                         min_years=3, requirements=(ReadRequirement("Backend", "core", "APIs"),))


def _persist(record):
    record["internal_diagnostics"] = {"pool": record.pop("pool")}
    return record


def _service(enricher, tmp_path):
    proposer = CapabilityProposer(InMemoryCapabilityMemory(),
                                  llm_proposer=lambda *a: LearnedCapability("", "Backend", ("APIs",), "Eng"))
    pipeline = Pipeline(
        intake=IntakeAgent(reader=_reader, capability_proposer=proposer, org="dayzero.partners"),
        briefing=BriefingAgent(), calibration=CalibrationAgent(),
        search=SearchAgent(_Provider(), page_size=50),
        ranking=RankingAgent(judge=_Judge(), enricher=enricher, screener=_KeepAll(), admit_n=2, show=5),
    )
    return IntakeService(pipeline, sessions=SearchStore(storage_dir=tmp_path / "s"),
                         confirmations=ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "c")))


def _searched(tmp_path):
    enricher = _CountingEnricher()
    svc = _service(enricher, tmp_path)
    cid = svc.confirm(svc.start("JD", {"hiring_company": "Acme", "country": "India", "work_mode": "remote"},
                                posted_title="Backend Engineer")["session_id"], edits={})["confirmation_id"]
    record = _persist(svc.run_search(cid, "s1"))
    enricher.n = 0   # reset after the first view so we count only campaign rounds
    return svc, record, enricher


def test_start_and_due_timing(tmp_path):
    svc, record, _ = _searched(tmp_path)
    c = svc.start_campaign(record, window_hours=72, budget=100, cadence_hours=2)
    assert c["status"] == "active"
    assert svc.campaign_due(record) is True                      # first round is due immediately
    t0 = datetime.now(timezone.utc)
    svc.campaign_round(record, now=t0)
    assert svc.campaign_due(record, now=t0 + timedelta(hours=1)) is False   # cadence not elapsed
    assert svc.campaign_due(record, now=t0 + timedelta(hours=2, minutes=1)) is True
    assert svc.campaign_due(record, now=t0 + timedelta(hours=100)) is False  # window closed


def test_round_paces_to_budget(tmp_path):
    svc, record, enricher = _searched(tmp_path)
    svc.start_campaign(record, budget=10, cadence_hours=2)        # budget below the per-round cap (15)
    r = svc.campaign_round(record)
    assert r["enriched"] == 10 and r["used"] == 10                # capped to the remaining budget
    assert r["status"] == "done" and r["done_reason"] == "budget"
    assert enricher.n == 10


def test_round_batches_then_exhausts(tmp_path):
    svc, record, enricher = _searched(tmp_path)
    svc.start_campaign(record, budget=100, cadence_hours=2)       # reserve = 23 (25 pulled − 2 admitted)
    r1 = svc.campaign_round(record)
    assert r1["enriched"] == 15 and r1["status"] == "active"      # one round = the per-round cap
    r2 = svc.campaign_round(record)
    assert r2["enriched"] == 8 and r2["status"] == "active"       # the remaining reserve
    r3 = svc.campaign_round(record)
    assert r3["enriched"] == 0 and r3["done_reason"] == "exhausted"
    assert enricher.n == 23                                       # the whole reserve, never more
