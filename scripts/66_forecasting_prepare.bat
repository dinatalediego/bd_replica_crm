@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10
echo [1/3] Validando contrato de absorcion...
".venv\Scripts\python.exe" scripts\schema_sync.py --only absorcion_ventas_mensual
if errorlevel 1 exit /b %ERRORLEVEL%
echo [2/3] Instalando tablas y vistas de forecasting...
".venv\Scripts\python.exe" scripts\schema_sync.py --only commercial_forecasting
if errorlevel 1 exit /b %ERRORLEVEL%
echo [3/3] Revisando unidades NP, SL y TZ...
".venv\Scripts\python.exe" scripts\commercial_forecasting.py review
if errorlevel 1 exit /b %ERRORLEVEL%
echo Preparacion completada. El siguiente paso es 64_forecasting_medallio.bat.
exit /b 0
