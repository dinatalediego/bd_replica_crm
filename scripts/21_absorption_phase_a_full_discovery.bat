@echo off
setlocal
cd /d "%~dp0\.."
set "PYTHONPATH=%CD%\src"
echo ADVERTENCIA: incluye probes mas pesados sobre procesos/proforma_unidad.
".venv\Scripts\python.exe" -m absorption_phase_a.runner --all
endlocal
