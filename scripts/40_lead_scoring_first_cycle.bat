@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10
".venv\Scripts\python.exe" "scripts\lead_scoring.py" cycle --capture-mode backfill
exit /b %ERRORLEVEL%
