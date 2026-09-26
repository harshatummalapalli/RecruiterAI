@echo off
REM Rebuild the saved intake fixtures (real intake code, canned model output, no network) and open the Living Brief preview.
cd /d "%~dp0"
.venv\Scripts\python.exe -m backend.experiments.intake_preview
cd frontend
start "" http://localhost:5173/preview-brief.html
npm run dev
