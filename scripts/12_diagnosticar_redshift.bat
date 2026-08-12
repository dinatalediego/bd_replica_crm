@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: No existe .venv. Ejecuta scripts\01_instalar.bat primero.
  exit /b 1
)
set "SCHEMA=%~1"
if "%SCHEMA%"=="" set "SCHEMA=grupocygnus"
set "TABLE=%~2"
if "%TABLE%"=="" set "TABLE=proforma_unidad"
".venv\Scripts\python.exe" -m replica_cygnus.redshift_diagnostics "%SCHEMA%" "%TABLE%"
exit /b %ERRORLEVEL%
