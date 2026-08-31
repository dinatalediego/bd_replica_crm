@echo off
setlocal
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

%PY% scripts\08_instalar_unidades_multifuente.py
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo [ERROR] No se pudo instalar core.v_unidades_fuentes. Codigo %RC%.
  exit /b %RC%
)

exit /b 0
