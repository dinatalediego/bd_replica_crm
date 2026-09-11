@echo off
setlocal
cd /d "%~dp0.."

echo =====================================================
echo MEDALLIO - ABSORCION HISTORICA MULTIPROYECTO
echo =====================================================
echo Fenix ^| Urbanzen ^| Tizon y Bueno
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

%PYTHON% scripts\absorption_history_export.py --mode multi
if errorlevel 1 goto :error

echo.
echo Reporte generado en:
echo   output\absorcion_historica\multiproyecto\
echo.
pause
endlocal
exit /b 0

:error
echo.
echo ERROR: no se pudo generar el Excel historico multiproyecto.
echo Revisa .env, PostgreSQL medallio_dw y la vista mensual del modulo 60.
pause
endlocal
exit /b 1
