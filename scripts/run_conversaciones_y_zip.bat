@echo off
setlocal
cd /d "%~dp0.."
call "scripts\run_conversaciones_manual.bat"
if errorlevel 1 exit /b %errorlevel%
call ".venv\Scripts\python.exe" "scripts\export_conversaciones_diagnostico.py"
exit /b %errorlevel%
