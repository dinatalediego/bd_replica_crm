@echo off
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
  echo Uso: scripts\07_cargar_raw_mercado.bat "C:\ruta\mercado.csv"
  exit /b 2
)

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

%PY% scripts\load_raw_mercado.py "%~1"
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo [ERROR] La carga raw_mercado fallo con codigo %RC%.
  exit /b %RC%
)

echo [OK] raw_mercado actualizado y validado.
exit /b 0
