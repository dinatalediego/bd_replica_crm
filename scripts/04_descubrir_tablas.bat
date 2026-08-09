@echo off
setlocal
cd /d "%~dp0.."
set SCHEMA=grupocygnus
if not "%~1"=="" set SCHEMA=%~1
call ".venv\Scripts\python.exe" -m replica_cygnus.cli discover --schema "%SCHEMA%"
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
