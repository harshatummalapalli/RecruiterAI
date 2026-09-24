@echo off
cd /d "%~dp0"
echo Starting CrustData Structured Search Playground on http://127.0.0.1:8765 (Ctrl+C to stop)
.venv\Scripts\python.exe -m backend.experiments.structured_playground
pause
