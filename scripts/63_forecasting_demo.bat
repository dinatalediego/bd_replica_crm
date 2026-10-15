@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10
".venv\Scripts\python.exe" "scripts\commercial_forecasting.py" demo
exit /b %ERRORLEVEL%
