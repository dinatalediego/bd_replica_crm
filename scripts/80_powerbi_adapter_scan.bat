@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] No existe .venv\Scripts\python.exe
  exit /b 10
)
call ".venv\Scripts\python.exe" ".\scripts\powerbi_adapter.py" scan %*
exit /b %ERRORLEVEL%
