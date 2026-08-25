@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: no existe .venv\Scripts\python.exe
  exit /b 10
)

call ".venv\Scripts\python.exe" -m pip install -r requirements-market.txt
if errorlevel 1 exit /b %ERRORLEVEL%

call ".venv\Scripts\python.exe" -m mercado_ingestion.cli init
exit /b %ERRORLEVEL%

