@echo off
setlocal
cd /d "%~dp0.."

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: No se encontro el lanzador de Python "py".
  echo Instala Python 3.11 o 3.12 y marca "Add Python to PATH".
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Buscando Python 3.12 o 3.11...
  py -3.12 --version >nul 2>nul
  if not errorlevel 1 (
    py -3.12 -m venv .venv
  ) else (
    py -3.11 --version >nul 2>nul
    if errorlevel 1 (
      echo ERROR: Se requiere Python 3.11 o 3.12.
      echo Instala una de esas versiones y vuelve a ejecutar este archivo.
      exit /b 1
    )
    py -3.11 -m venv .venv
  )
  if errorlevel 1 exit /b 1
)

call ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1
call ".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 exit /b 1

if not exist ".env" copy ".env.example" ".env" >nul
if not exist "config\tables.yml" copy "config\tables.example.yml" "config\tables.yml" >nul
if not exist "config\decision_systems.yml" copy "config\decision_systems.example.yml" "config\decision_systems.yml" >nul

echo.
echo Instalacion/actualizacion completada.
echo 1. Revisa .env con tus credenciales.
echo 2. Verifica la base medallio_dw en PostgreSQL local.
echo 3. Ejecuta scripts\02_probar_conexiones.bat
echo 4. Ejecuta scripts\03_inicializar_postgres.bat
echo 5. Ejecuta scripts\10_validar_contratos_decision.bat
echo 6. Ejecuta scripts\11_demo_decisiones.bat
endlocal
