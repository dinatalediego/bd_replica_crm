@echo off
setlocal
cd /d "%~dp0.."

set "DEFAULT_FILE=C:\Cygnus\otros_proyectos\amma_torre_marsano\unidades_ready.csv"

if "%~1"=="" (
  set "SOURCE_FILE=%DEFAULT_FILE%"
) else (
  set "SOURCE_FILE=%~1"
)

if not exist "%SOURCE_FILE%" (
  echo [ERROR] No existe el archivo: %SOURCE_FILE%
  echo Uso opcional: scripts\07_cargar_raw_mercado.bat "C:\ruta\archivo.csv"
  exit /b 2
)

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo [INFO] Fuente: %SOURCE_FILE%
echo [INFO] Destino: raw_mercado.unidades

%PY% scripts\load_raw_mercado.py "%SOURCE_FILE%"
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo [ERROR] La carga raw_mercado fallo con codigo %RC%.
  exit /b %RC%
)

echo [OK] raw_mercado.unidades actualizado y validado.
exit /b 0
