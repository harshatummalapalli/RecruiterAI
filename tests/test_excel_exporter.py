from pathlib import Path

from backend.exporters.excel import ExcelExporter
from backend.models.candidate import Candidate


def test_export_writes_ranked_candidates_to_excel(tmp_path: Path) -> None:
    export_path = tmp_path / "candidates.xlsx"
    exporter = ExcelExporter()

    candidates = [
        Candidate(
            name="Alice",
            title="Machine Learning Engineer",
            company="OpenAI",
            location="New York, US",
            provider_score=0.95,
            final_score=9.5,
            profile_url="https://example.com/alice",
            source="crustdata",
        )
    ]

    exporter.export(candidates, str(export_path))

    assert export_path.exists()
    assert export_path.stat().st_size > 0
