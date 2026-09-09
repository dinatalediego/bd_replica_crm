@echo off
setlocal
cd /d "%~dp0.."

echo =====================================================
echo MEDALLIO - MOVIMIENTO DE STOCK MENSUAL A EXCEL
echo =====================================================
echo Fenix ^| Urbanzen ^| Tizon y Bueno
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

set "MONTH=%~1"

if "%MONTH%"=="" (
    echo Mes: actual
) else (
    echo Mes: %MONTH%
)

echo.
echo [1/2] Validando e instalando capa mensual...
%PYTHON% scripts\monthly_stock_movement_export.py --install-only
if errorlevel 1 goto :error

echo [2/2] Generando Excel...
if "%MONTH%"=="" (
    %PYTHON% scripts\monthly_stock_movement_export.py
) else (
    %PYTHON% scripts\monthly_stock_movement_export.py --month %MONTH%
)
if errorlevel 1 goto :error

echo.
echo Reporte generado en: output\movimiento_stock_mensual\
echo Puedes indicar otro mes asi:
echo   scripts\60_exportar_movimiento_stock_mensual.bat 2026-08
echo.
pause
endlocal
exit /b 0

:error
echo.
echo ERROR: no se pudo generar el reporte mensual.
echo Revisa .env, PostgreSQL medallio_dw y la capa de absorcion v1.1.
pause
endlocal
exit /b 1
