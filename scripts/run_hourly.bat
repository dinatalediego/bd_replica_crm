@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10

call ".venv\Scripts\python.exe" -m replica_cygnus.cli sync
set SYNC_RC=%ERRORLEVEL%

rem Aunque falle una tabla, intentamos registrar el estado para que Power BI lo vea.
call ".venv\Scripts\python.exe" -m replica_cygnus.cli observe --mode hourly
set OBS_RC=%ERRORLEVEL%

if not "%SYNC_RC%"=="0" exit /b %SYNC_RC%
exit /b %OBS_RC%
