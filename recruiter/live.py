"""Assemble the REAL pipeline — live reader, OpenAI capability proposer, and the
CrustData / Harvest / Judge keeper adapters. Construction is offline (no network,
no credits); the first CrustData call happens only when you run a search.
"""

from __future__ import annotations

import os
from pathlib import Path

from recruiter.agents.briefing import BriefingAgent
from recruiter.agents.calibration import CalibrationAgent
from recruiter.agents.intake import IntakeAgent
from recruiter.agents.intake.capability_memory import FileCapabilityMemory
from recruiter.agents.intake.capability_proposal import CapabilityProposer
from recruiter.agents.intake.llm_proposer import make_proposer
from recruiter.agents.intake.native_reader import make_native_reader
from recruiter.agents.ranking import RankingAgent
from recruiter.agents.ranking.judge_adapter import JudgeAdapter
from recruiter.agents.search import SearchAgent
from recruiter.config import CAPABILITY_MODEL, JUDGE_MODEL, READER_MODEL
from recruiter.pipeline import Pipeline
from recruiter.providers.crustdata_adapter import CrustDataAdapter
from recruiter.providers.harvest_adapter import HarvestAdapter

_DEFAULT_MEMORY_ROOT = Path("output/capability_memory")


def build_live_pipeline(
    org: str = "default",
    *,
    memory_root: Path = _DEFAULT_MEMORY_ROOT,
    page_size: int = 50,
    # judge-N / show-few hedge: pull ~page_size, baseline-rank the whole pool for
    # free, judge only the top admit_n, show the best `show`. The rest is held in
    # reserve and judged on demand. admit_n=8/show=5 pays the Judge for 8 (not 25)
    # on the first view — cheaper + faster — with a Judge-ranked first impression.
    admit_n: int = int(os.environ.get("RECRUITER_ADMIT_N") or 8),
    show: int = 5,
    judge_workers: int = int(os.environ.get("RECRUITER_JUDGE_WORKERS") or 8),
    reader_model: str = READER_MODEL,
    capability_model: str = CAPABILITY_MODEL,
    judge_model: str = JUDGE_MODEL,
) -> Pipeline:
    intake = IntakeAgent(
        reader=make_native_reader(reader_model),
        capability_proposer=CapabilityProposer(
            FileCapabilityMemory(memory_root), make_proposer(model=capability_model)
        ),
        org=org,
    )
    return Pipeline(
        intake=intake,
        briefing=BriefingAgent(),
        calibration=CalibrationAgent(),
        search=SearchAgent(CrustDataAdapter(), page_size=page_size),
        ranking=RankingAgent(
            judge=JudgeAdapter(model=judge_model), enricher=HarvestAdapter(),
            admit_n=admit_n, show=show, max_judge_workers=judge_workers,
        ),
    )
