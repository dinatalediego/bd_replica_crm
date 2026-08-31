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
  echo [ERROR] No existe el archivo de mercado: "%SOURCE_FILE%"
  exit /b 2
)

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo [1/2] Cargando raw_mercado.unidades desde "%SOURCE_FILE%"...
%PY% scripts\load_raw_mercado.py "%SOURCE_FILE%" --schema raw_mercado --table unidades
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo [ERROR] La carga raw_mercado fallo con codigo %RC%.
  exit /b %RC%
)

echo [2/2] Actualizando capa multifuente y analitica comparativa...
%PY% scripts\08_instalar_unidades_multifuente.py
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo [ERROR] raw_mercado cargo correctamente, pero fallo la capa comparativa. Codigo %RC%.
  exit /b %RC%
)

echo [OK] Ciclo completo: raw_mercado + core multifuente + analytics comparativa.
exit /b 0
