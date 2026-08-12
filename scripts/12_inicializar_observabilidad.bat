@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: No existe .venv. Ejecuta scripts\01_instalar.bat
  exit /b 10
)
call ".venv\Scripts\python.exe" -m replica_cygnus.cli observability-init
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
