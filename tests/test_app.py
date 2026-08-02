from backend.app import RecruiterAIApp
from backend.models.candidate import Candidate
from backend.models.search_intent import SearchIntent
from backend.services.candidate_ranker import CandidateRanker
from backend.services.jd_parser import JDParser
from backend.services.search_planner import SearchPlanner


class FakeParser:
    def parse(self, job_description: str) -> SearchIntent:
        return SearchIntent()


class FakePlanner:
    def build(self, intent: SearchIntent):
        return object()


class FakeProvider:
    def search(self, plan):
        return [Candidate(name="Alice", provider_score=0.9)]


class FakeRanker:
    def rank(self, candidates, intent):
        return candidates


class FakeExporter:
    def export(self, candidates, output_path: str) -> None:
        self.exported_path = output_path
        self.exported_candidates = candidates


def test_recruiter_ai_app_runs_pipeline_end_to_end() -> None:
    parser = FakeParser()
    planner = FakePlanner()
    provider = FakeProvider()
    ranker = FakeRanker()
    exporter = FakeExporter()

    app = RecruiterAIApp(
        jd_parser=parser,
        search_planner=planner,
        provider=provider,
        candidate_ranker=ranker,
        excel_exporter=exporter,
    )

    ranked = app.run("Software engineer role", "out.xlsx")

    assert len(ranked) == 1
    assert ranked[0].name == "Alice"
    assert exporter.exported_path == "out.xlsx"
    assert exporter.exported_candidates[0].name == "Alice"
