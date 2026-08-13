@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: no existe .venv\Scripts\python.exe
  exit /b 1
)
".venv\Scripts\python.exe" ".\src\absorption_reconciliation\install.py"
endlocal
