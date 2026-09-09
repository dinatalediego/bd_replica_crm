@echo off
setlocal
cd /d "%~dp0.."

echo ================================================
echo MEDALLIO - STOCK DISPONIBLE A EXCEL
echo Fenix ^| Urbanzen ^| Tizon y Bueno
echo ================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

%PYTHON% scripts\stock_export.py --install-view
if errorlevel 1 (
    echo.
    echo ERROR: no se pudo generar el reporte.
    echo Revisa .env, PostgreSQL medallio_dw y dependencias.
    pause
    exit /b 1
)

echo.
echo Reporte generado en: output\stock_disponible\
echo.
pause
endlocal
