@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10

rem Instala/repara el contrato DQ si cambió y refresca los datos de clientes.
call ".venv\Scripts\python.exe" ".\scripts\schema_sync.py" --only clientes_calidad
if errorlevel 1 exit /b %ERRORLEVEL%

call ".venv\Scripts\python.exe" ".\scripts\refresh_clientes_calidad.py"
exit /b %ERRORLEVEL%
