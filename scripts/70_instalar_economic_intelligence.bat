@echo off
setlocal
cd /d "%~dp0.."

echo =====================================================
echo MEDALLIO - ECONOMIC INTELLIGENCE OS
echo =====================================================
echo Feature mart ^| Micro ^| Macro ^| Forecast ^| PMO

echo.
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

%PYTHON% scripts\70_instalar_economic_intelligence.py
if errorlevel 1 goto :error

echo.
echo OK. Abre: notebooks\economic_intelligence\00_contrato_y_auditoria.ipynb
endlocal
exit /b 0

:error
echo.
echo ERROR: no se pudo preparar Economic Intelligence.
echo Revisa Medallio DW y que la capa 60 de movimiento mensual este disponible.
endlocal
exit /b 1
