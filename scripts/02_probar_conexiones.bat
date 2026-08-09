@echo off
setlocal
cd /d "%~dp0.."
call ".venv\Scripts\python.exe" -m replica_cygnus.cli test-connections
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
