@echo off
setlocal
cd /d "%~dp0\.."
".venv\Scripts\python.exe" ".\src\absorption_phase_b\run_backfill.py"
endlocal
