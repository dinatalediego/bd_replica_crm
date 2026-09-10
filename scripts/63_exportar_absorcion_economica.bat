@echo off
setlocal
cd /d "%~dp0.."

echo =====================================================
echo MEDALLIO - ABSORCION ECONOMICA A EXCEL
echo =====================================================
echo Universo actual completo ^+ historia observada del ledger

echo.
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

%PYTHON% scripts\economic_intelligence_export.py
if errorlevel 1 goto :error

echo.
echo Reporte generado en: output\economic_intelligence\
pause
endlocal
exit /b 0

:error
echo.
echo ERROR: no se pudo generar Absorcion Economica.
echo Revisa Medallio DW y la vista mensual 60.
pause
endlocal
exit /b 1
