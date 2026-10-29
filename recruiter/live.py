"""Assemble the REAL pipeline — live reader, OpenAI capability proposer, and the
CrustData / Harvest / Judge keeper adapters. Construction is offline (no network,
no credits); the first CrustData call happens only when you run a search.
"""

from __future__ import annotations

from pathlib import Path

from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake import IntakeAgent
from recruiter.agents.intake.capability_memory import FileCapabilityMemory
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.llm_proposer import make_openai_proposer
from recruiter.agents.intake.reader import keeper_reader
from recruiter.agents.ranking import RankingAgent
from recruiter.agents.ranking.judge_adapter import JudgeAdapter
from recruiter.agents.search import SearchAgent
from recruiter.pipeline import Pipeline
from recruiter.providers.crustdata_adapter import CrustDataAdapter
from recruiter.providers.harvest_adapter import HarvestAdapter

_DEFAULT_MEMORY_ROOT = Path("output/capability_memory")


def build_live_pipeline(
    org: str = "default",
    *,
    memory_root: Path = _DEFAULT_MEMORY_ROOT,
    page_size: int = 50,
    admit_n: int = 25,
    show: int = 5,
    capability_model: str = "gpt-4o-mini",
) -> Pipeline:
    intake = IntakeAgent(
        reader=keeper_reader,
        capability_proposer=CapabilityProposer(
            FileCapabilityMemory(memory_root), make_openai_proposer(model=capability_model)
        ),
        org=org,
    )
    return Pipeline(
        intake=intake,
        briefing=BriefingAgent(),
        calibration=CalibrationAgent(),
        search=SearchAgent(CrustDataAdapter(), page_size=page_size),
        ranking=RankingAgent(judge=JudgeAdapter(), enricher=HarvestAdapter(), admit_n=admit_n, show=show),
    )
