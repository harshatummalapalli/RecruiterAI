"""STEER — refine reaches the un-enriched reserve: cheap-screen the new intent,
enrich + judge only the matches, leave the rest. Offline, fakes count enrichment."""

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


def _cands():
    out = []
    for i in range(2):
        out.append(CandidateRecord(f"be{i}", name=f"Backend {i}", title="Backend Engineer",
                                   location="Pune, India", raw={"basic_profile": {"headline": "APIs"}},
                                   matched_queries=("natural_language",)))
    for i in range(4):
        out.append(CandidateRecord(f"fe{i}", name=f"Frontend {i}", title="Frontend Engineer",
                                   location="Pune, India", raw={"basic_profile": {"headline": "React"}},
                                   matched_queries=("natural_language",)))
    return out


class _Provider:
    def count(self, query): return 4321
    def search(self, query, page_size): return _cands()


class _Judge:
    def judge(self, role, record):
        return tuple({"tier": r.tier, "signal_text": r.text, "quote": r.text, "verdict": "met"} for r in role.requirements)


class _KeywordScreener:
    """Keeps a candidate only if its title contains a core-requirement word."""
    def screen(self, role, records, feedback_context=None):
        terms = [r.text.lower().split()[0] for r in role.tier("core")]
        return tuple(ScreenResult(keep=any(t in (rec.title or "").lower() for t in terms), score=1.0) for rec in records)


class _CountingEnricher:
    def __init__(self): self.enriched = []
    def enrich(self, record):
        record.enriched = True
        self.enriched.append(record.candidate_id)


def _reader(notes, posted_title=None):
    return Understanding(identity="Backend Engineer", posted_title="Backend Engineer", posted_title_source="jd",
                         min_years=3, requirements=(ReadRequirement("Backend", "core", "APIs"),))


def _persist(record):
    """Mirror the API: the bridge returns the held pool under "pool"; persistence
    lifts it into internal_diagnostics (what refine reads)."""
    record["internal_diagnostics"] = {"pool": record.pop("pool")}
    return record


def _service(enricher, tmp_path):
    pipe = type("P", (), {})()
    proposer = CapabilityProposer(InMemoryCapabilityMemory(),
                                  llm_proposer=lambda *a: LearnedCapability("", "Backend", ("APIs",), "Eng"))
    from recruiter.pipeline import Pipeline
    pipeline = Pipeline(
        intake=IntakeAgent(reader=_reader, capability_proposer=proposer, org="dayzero.partners"),
        briefing=BriefingAgent(), calibration=CalibrationAgent(),
        search=SearchAgent(_Provider(), page_size=50),
        ranking=RankingAgent(judge=_Judge(), enricher=enricher, screener=_KeywordScreener(), admit_n=2, show=5),
    )
    return IntakeService(pipeline, sessions=SearchStore(storage_dir=tmp_path / "s"),
                         confirmations=ConfirmationStore(store=SearchStore(storage_dir=tmp_path / "c")))


def test_refine_enriches_only_the_reserve_that_matches_the_new_intent(tmp_path):
    enricher = _CountingEnricher()
    svc = _service(enricher, tmp_path)
    cid = svc.confirm(svc.start("JD", {"hiring_company": "Acme", "country": "India", "work_mode": "remote"},
                                posted_title="Backend Engineer")["session_id"], edits={})["confirmation_id"]
    record = _persist(svc.run_search(cid, "s1"))

    # First view: only the 2 Backend passed the screen + admit_n=2 → enriched. The 4
    # Frontend failed the screen → they sit in the reserve, UN-enriched.
    assert sorted(enricher.enriched) == ["be0", "be1"]
    assert len(record["internal_diagnostics"]["pool"]["reserve"]) == 4

    # Change tracks: now I also want Frontend. STEER should screen the reserve against
    # the new intent, enrich ONLY the matches (all 4 frontend here), and surface them.
    outcome = svc.refine(record, {"add_requirements": [{"text": "Frontend", "tier": "core"}]})
    assert outcome["reserve_enriched"] == 4
    assert outcome["reserve_remaining"] == 0
    assert sorted(enricher.enriched) == ["be0", "be1", "fe0", "fe1", "fe2", "fe3"]   # the 4 reserve now enriched


def test_refine_leaves_non_matching_reserve_untouched(tmp_path):
    enricher = _CountingEnricher()
    svc = _service(enricher, tmp_path)
    cid = svc.confirm(svc.start("JD", {"hiring_company": "Acme", "country": "India", "work_mode": "remote"},
                                posted_title="Backend Engineer")["session_id"], edits={})["confirmation_id"]
    record = _persist(svc.run_search(cid, "s1"))

    # A refine that doesn't open a new lane (still Backend-only) must not pay to
    # enrich the Frontend reserve — they don't match, so they stay put.
    before = list(enricher.enriched)
    outcome = svc.refine(record, {"min_years": 2})
    assert outcome["reserve_enriched"] == 0
    assert enricher.enriched == before                       # nobody new enriched
    assert outcome["reserve_remaining"] == 4                  # the frontend reserve untouched
