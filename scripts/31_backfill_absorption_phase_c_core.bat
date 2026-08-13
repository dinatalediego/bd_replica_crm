@echo off
setlocal
cd /d "%~dp0\.."
".venv\Scripts\python.exe" ".\src\absorption_phase_c\backfill.py"
endlocal
