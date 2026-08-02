import logging
from pathlib import Path
from typing import Any

from backend.app import RecruiterAIApp
from backend.exporters.excel import ExcelExporter
from backend.models.candidate import Candidate
from backend.models.search_intent import SearchIntent
from backend.providers.mock_response import MOCK_RAW_RESPONSE
from backend.services.candidate_ranker import CandidateRanker
from backend.services.jd_parser import JDParser
from backend.services.search_planner import SearchPlanner
from backend.providers.base import BaseLLMProvider

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


class MockJDParser(BaseLLMProvider):
    def parse_job_description(self, job_description: str) -> SearchIntent:
        from backend.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        return provider._build_search_intent(MOCK_RAW_RESPONSE)


class MockSearchProvider:
    def search(self, plan: Any) -> list[Candidate]:
        return [
            Candidate(
                name="Alice Example",
                title="Senior Python Engineer",
                company="OpenAI",
                location="New York, US",
                provider_score=0.95,
                final_score=9.5,
                profile_url="https://example.com/alice",
                source="mock",
                raw_data={"skills": ["Python", "FastAPI"]},
            )
        ]


def main() -> None:
    root = Path(__file__).resolve().parent
    jd_path = root / "sample_jd.txt"
    output_path = root / "output" / "results.xlsx"

    try:
        jd_text = jd_path.read_text(encoding="utf-8")
        app = RecruiterAIApp(
            jd_parser=JDParser(provider=MockJDParser()),
            search_planner=SearchPlanner(),
            provider=MockSearchProvider(),
            candidate_ranker=CandidateRanker(),
            excel_exporter=ExcelExporter(),
        )
        ranked_candidates = app.run(jd_text, str(output_path))

        logger.info("SearchIntent:")
        logger.info("  (parsed by OpenAI provider during execution)")
        logger.info("SearchPlan:")
        logger.info("  (built by SearchPlanner during execution)")
        logger.info("Number of candidates returned: %s", len(ranked_candidates))
        logger.info("Top 5 ranked candidates:")
        for candidate in ranked_candidates[:5]:
            logger.info("- %s | %s | %s", candidate.name, candidate.company, candidate.final_score)
        logger.info("Results saved to: %s", output_path)
    except Exception:
        logger.exception("Recruiter pipeline failed")


if __name__ == "__main__":
    main()
