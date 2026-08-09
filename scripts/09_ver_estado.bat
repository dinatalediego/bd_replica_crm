@echo off
setlocal
cd /d "%~dp0.."
call ".venv\Scripts\python.exe" -m replica_cygnus.cli status --limit 30
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
