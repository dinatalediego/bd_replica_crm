@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10

call ".venv\Scripts\python.exe" ".\scripts\schema_sync.py" --only portal_conversion
if errorlevel 1 exit /b %ERRORLEVEL%

call ".venv\Scripts\python.exe" ".\scripts\refresh_clientes_calidad.py"
if errorlevel 1 exit /b %ERRORLEVEL%

call ".venv\Scripts\python.exe" ".\scripts\refresh_portal_conversion.py" --start-year 2026
exit /b %ERRORLEVEL%
