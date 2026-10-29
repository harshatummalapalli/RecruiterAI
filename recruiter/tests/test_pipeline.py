"""End-to-end orchestration — notes + boundary -> ranked candidates, fully
offline (every I/O dep faked, zero credits)."""

from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake import IntakeAgent
from recruiter.agents.intake.capability_memory import InMemoryCapabilityMemory, LearnedCapability
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.model import ReadRequirement, Understanding
from recruiter.agents.ranking import RankingAgent
from recruiter.agents.search import SearchAgent
from recruiter.candidates import CandidateRecord
from recruiter.pipeline import Pipeline

NOTES = (
    "AI Architect, came from a Java background, now building Agentic Systems and AI in "
    "production, strong Python, 12+ years, India (prefer Hyderabad/Bengaluru/Pune), IC, for Epiq."
)
BOUNDARY = {"hiring_company": "Epiq", "country": "India", "work_mode": "remote",
            "preferred_cities": ["Hyderabad", "Bengaluru", "Pune"]}


def _understanding(notes, posted_title=None):
    return Understanding(
        identity="AI Architect", posted_title="AI Architect", posted_title_source="recruiter",
        min_years=12, work_mode_in_notes="remote",
        requirements=(
            ReadRequirement("Agentic Systems", "core", when="current"),
            ReadRequirement("Python", "core", when="current"),
            ReadRequirement("Java", "core", when="past"),
        ),
    )


class _FakeProvider:
    def search(self, query, page_size):
        return [
            CandidateRecord("real", name="real", title="AI Architect", location="Hyderabad, India",
                            raw={"basic_profile": {"headline": "Agentic Systems, Python, LLMs in production"}},
                            matched_queries=("natural_language", "title_expansion")),
            CandidateRecord("weak", name="weak", title="AI Architect", location="Pune, India",
                            raw={"basic_profile": {"headline": "generalist consultant"}},
                            matched_queries=("natural_language",)),
            CandidateRecord("faraway", name="faraway", title="AI Architect", location="Berlin, Germany",
                            raw={"basic_profile": {"headline": "Agentic Python"}}),
        ]


class _FakeJudge:
    def judge(self, role, record):
        hl = ((record.raw.get("basic_profile") or {}).get("headline") or "").lower()
        return tuple(
            {"tier": r.tier, "signal_text": r.text,
             "verdict": "met" if r.text.split()[0].lower() in hl else "not_evidenced",
             "quote": r.text if r.text.split()[0].lower() in hl else ""}
            for r in role.requirements
        )


def _pipeline():
    proposer = CapabilityProposer(
        InMemoryCapabilityMemory(),
        llm_proposer=lambda *a: LearnedCapability("", "Agentic AI", ("agentic", "LLM", "RAG"), "AI"),
    )
    intake = IntakeAgent(reader=_understanding, capability_proposer=proposer, org="epiq")
    return Pipeline(
        intake=intake,
        briefing=BriefingAgent(),
        calibration=CalibrationAgent(),
        search=SearchAgent(_FakeProvider(), page_size=50),
        ranking=RankingAgent(judge=_FakeJudge(), admit_n=25, show=5),
    )


def test_end_to_end_notes_to_ranked_candidates():
    result = _pipeline().run_all(NOTES, BOUNDARY, refinement_answers={"dealbreakers": ["Agentic Systems", "Python"]})

    assert not result.blocked
    assert result.authorization.authorized
    # Geo net dropped the Berlin profile; India + unknowns kept.
    assert result.search.geo_dropped == 1
    # The real match (Agentic + Python evidence) is surfaced first.
    assert result.ranking.shown[0].record.candidate_id == "real"
    assert "Evidence:" in result.ranking.shown[0].fit
    # Dealbreakers were applied to the model the search/rank ran on.
    hard = {r.text for r in result.model.requirements if r.hard}
    assert hard == {"Agentic Systems", "Python"}
    # Recruiter review carried no query internals.
    blob = " ".join(f"{ln.label} {ln.value}" for ln in result.review.summary).lower()
    assert "query" not in blob and "keyword" not in blob


def test_missing_years_blocks_before_any_search():
    def _no_years(notes, posted_title=None):
        return Understanding(identity="AI Architect", min_years=None,
                             requirements=(ReadRequirement("Agentic Systems", "core"),))
    pipe = _pipeline()
    pipe.intake = IntakeAgent(reader=_no_years,
                              capability_proposer=CapabilityProposer(InMemoryCapabilityMemory()), org="epiq")
    result = pipe.run_all(NOTES, {"country": "India", "work_mode": "remote"})
    assert result.blocked
    assert [q.kind for q in result.outcome.clarifications] == ["min_years"]
    assert result.ranking is None       # nothing searched


def test_confirm_level_no_blocks_execution():
    result = _pipeline().run_all(NOTES, BOUNDARY, refinement_answers={"confirm_level": "no"})
    assert result.blocked and not result.authorization.authorized
    assert result.ranking is None
