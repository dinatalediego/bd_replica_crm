@echo off
setlocal
cd /d "%~dp0\.."
set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m absorption_phase_a.runner --metadata-only
endlocal
