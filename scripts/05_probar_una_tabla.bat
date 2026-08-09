@echo off
setlocal
cd /d "%~dp0.."
set TABLE=clientes_proyectos
if not "%~1"=="" set TABLE=%~1

echo Validando %TABLE%...
call ".venv\Scripts\python.exe" -m replica_cygnus.cli validate --only "%TABLE%" --include-disabled
if errorlevel 1 (
  echo La validacion fallo. Revisa config\tables.yml.
  pause
  exit /b 1
)

echo.
echo Ejecutando prueba limitada a 500 filas...
call ".venv\Scripts\python.exe" -m replica_cygnus.cli sync --only "%TABLE%" --include-disabled --max-rows 500
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
