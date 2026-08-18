@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10

rem 1) Replica RAW desde Redshift.
call ".venv\Scripts\python.exe" -m replica_cygnus.cli sync
set SYNC_RC=%ERRORLEVEL%
if not "%SYNC_RC%"=="0" goto OBSERVE_AND_EXIT

rem 2) Refresca dimensiones CORE de estado actual.
call ".venv\Scripts\python.exe" ".\scripts\core_commercial.py" refresh
set CORE_RC=%ERRORLEVEL%
if not "%CORE_RC%"=="0" goto OBSERVE_AND_EXIT

rem 3) Refresca ciclo comercial/absorcion solo si hubo cambios en el lookback.
call ".venv\Scripts\python.exe" ".\src\absorption_phase_b\run_incremental.py"
set LIFECYCLE_RC=%ERRORLEVEL%
if not "%LIFECYCLE_RC%"=="0" goto OBSERVE_AND_EXIT

:OBSERVE_AND_EXIT
rem Siempre intentamos registrar observabilidad para que Power BI vea el estado.
call ".venv\Scripts\python.exe" -m replica_cygnus.cli observe --mode hourly
set OBS_RC=%ERRORLEVEL%

if defined SYNC_RC if not "%SYNC_RC%"=="0" exit /b %SYNC_RC%
if defined CORE_RC if not "%CORE_RC%"=="0" exit /b %CORE_RC%
if defined LIFECYCLE_RC if not "%LIFECYCLE_RC%"=="0" exit /b %LIFECYCLE_RC%
exit /b %OBS_RC%
