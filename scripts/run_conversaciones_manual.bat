@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Falta .venv\Scripts\python.exe
  exit /b 2
)
call ".venv\Scripts\python.exe" "scripts\schema_sync.py" --only conversaciones
if errorlevel 1 exit /b %errorlevel%
call ".venv\Scripts\python.exe" "scripts\import_conversaciones.py"
exit /b %errorlevel%
