@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo No existe .venv. Ejecutando instalacion completa...
  call "%~dp0\01_instalar.bat"
  exit /b %ERRORLEVEL%
)

call ".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 exit /b 1

if not exist "config\observability.yml" copy "config\observability.example.yml" "config\observability.yml" >nul

echo.
echo Actualizacion de codigo a v0.3.0 completada.
echo NO se modificaron .env ni config\tables.yml.
echo Siguiente:
echo   1. scripts\03_inicializar_postgres.bat
echo   2. scripts\12_inicializar_observabilidad.bat
echo   3. scripts\13_observar_ahora.bat
endlocal
