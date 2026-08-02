import logging
from typing import List

from backend.models.candidate import Candidate
from backend.models.search_intent import SearchIntent
from backend.providers.base import BaseProvider
from backend.services.candidate_ranker import CandidateRanker
from backend.services.jd_parser import JDParser
from backend.services.search_planner import SearchPlanner

logger = logging.getLogger(__name__)


class ExcelExporter:
    """Simple exporter interface for ranked candidates."""

    def export(self, candidates: List[Candidate], output_path: str) -> None:
        """Export a list of candidates to an Excel file."""
        raise NotImplementedError


class RecruiterAIApp:
    """Coordinate parsing, search, ranking, and export for recruiter workflows."""

    def __init__(
        self,
        jd_parser: JDParser,
        search_planner: SearchPlanner,
        provider: BaseProvider,
        candidate_ranker: CandidateRanker,
        excel_exporter: ExcelExporter,
    ) -> None:
        self._jd_parser = jd_parser
        self._search_planner = search_planner
        self._provider = provider
        self._candidate_ranker = candidate_ranker
        self._excel_exporter = excel_exporter

    def run(self, jd_text: str, output_path: str) -> List[Candidate]:
        """Run the full pipeline from job description text to ranked Excel export."""
        logger.info("Parsing job description")
        intent: SearchIntent = self._jd_parser.parse(jd_text)

        logger.info("Building search plan")
        plan = self._search_planner.build(intent)

        if hasattr(plan, "searches") and not plan.searches:
            logger.warning("Search plan did not contain any searches")

        logger.info("Executing candidate search")
        candidates = self._provider.search(plan)

        if not candidates:
            logger.warning("No candidates were returned by the provider")

        logger.info("Ranking candidates")
        ranked_candidates = self._candidate_ranker.rank(candidates, intent)

        logger.info("Exporting ranked candidates")
        self._excel_exporter.export(ranked_candidates, output_path)

        return ranked_candidates
