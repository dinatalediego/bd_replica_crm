@echo off
setlocal
cd /d "%~dp0.."
if "%~1"=="" (
  echo Uso: scripts\46_lead_pilot_status.bat cygnus_contact_v1
  exit /b 1
)
".venv\Scripts\python.exe" scripts\lead_pilot.py status --pilot "%~1"
exit /b %errorlevel%
