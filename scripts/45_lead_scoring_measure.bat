@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10
".venv\Scripts\python.exe" "scripts\lead_scoring.py" outcomes
if errorlevel 1 exit /b %ERRORLEVEL%
".venv\Scripts\python.exe" "scripts\lead_scoring.py" measure
exit /b %ERRORLEVEL%
