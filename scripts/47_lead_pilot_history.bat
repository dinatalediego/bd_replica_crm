@echo off
setlocal
cd /d "%~dp0.."
".venv\Scripts\python.exe" scripts\lead_pilot_history.py %*
exit /b %errorlevel%
