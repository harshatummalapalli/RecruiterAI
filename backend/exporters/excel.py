from pathlib import Path
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Font

from backend.models.candidate import Candidate


class ExcelExporter:
    """Export ranked candidates to an Excel workbook."""

    def export(self, candidates: List[Candidate], output_path: str) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Candidates"

        headers = [
            "Rank",
            "Name",
            "Title",
            "Company",
            "Location",
            "Provider Score",
            "Final Score",
            "Profile URL",
            "Source",
        ]
        sheet.append(headers)

        for index, candidate in enumerate(candidates, start=1):
            sheet.append(
                [
                    index,
                    candidate.name or "",
                    candidate.title or "",
                    candidate.company or "",
                    candidate.location or "",
                    candidate.provider_score if candidate.provider_score is not None else "",
                    candidate.final_score if candidate.final_score is not None else "",
                    candidate.profile_url or "",
                    candidate.source or "",
                ]
            )

        header_font = Font(bold=True)
        for cell in sheet[1]:
            cell.font = header_font

        sheet.freeze_panes = "A2"

        for column in sheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                if cell.value is None:
                    continue
                max_length = max(max_length, len(str(cell.value)))
            sheet.column_dimensions[column_letter].width = min(max_length + 2, 50)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(output)
