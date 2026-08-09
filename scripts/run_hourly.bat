@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10
call ".venv\Scripts\python.exe" -m replica_cygnus.cli sync
exit /b %ERRORLEVEL%
