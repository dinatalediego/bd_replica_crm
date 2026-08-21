@echo off
setlocal
cd /d "%~dp0.."
if "%~1"=="" echo Uso: scripts\44_lead_scoring_promote.bat MODEL_RUN_ID "APROBADO_POR" & exit /b 2
if "%~2"=="" echo Uso: scripts\44_lead_scoring_promote.bat MODEL_RUN_ID "APROBADO_POR" & exit /b 2
if not exist ".venv\Scripts\python.exe" exit /b 10
".venv\Scripts\python.exe" "scripts\lead_scoring.py" promote --model-run-id "%~1" --approved-by "%~2"
exit /b %ERRORLEVEL%
