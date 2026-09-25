@echo off
REM Rebuild the sample record data (Toronto search, no network calls) and open the local record preview.
REM To preview another saved search:  preview_record.bat path\to\search.json --intent path\to\intent.json
cd /d "%~dp0"
if "%~1"=="" (
  .venv\Scripts\python.exe -m backend.experiments.record_preview output\record_preview\toronto_search.json --intent output\record_preview\toronto_intent.json
) else (
  .venv\Scripts\python.exe -m backend.experiments.record_preview %*
)
cd frontend
start "" http://localhost:5173/preview.html
npm run dev
