@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10

set MEDIO=%~1
if "%MEDIO%"=="" set MEDIO=all
set YEAR=%~2
if "%YEAR%"=="" set YEAR=2026

call ".venv\Scripts\python.exe" ".\scripts\export_portal_conversion_excel.py" --medio "%MEDIO%" --year %YEAR%
exit /b %ERRORLEVEL%
