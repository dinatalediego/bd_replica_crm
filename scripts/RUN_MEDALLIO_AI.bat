@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PROFILE=%~1"
if "%PROFILE%"=="" set "PROFILE=auto"

if /I "%MEDALLIO_AI_FORCE_LOCAL%"=="1" goto :local

where docker >nul 2>&1 || goto :local
docker info >nul 2>&1 || goto :local
docker compose version >nul 2>&1 || goto :local

if /I "%MEDALLIO_AI_REBUILD%"=="1" goto :build
docker image inspect medallio-ai:local >nul 2>&1 && goto :docker_run

:build
echo [Medallio AI] Construyendo imagen local...
docker compose -f compose.ai.yml build medallio-ai
if errorlevel 1 goto :local

:docker_run
echo [Medallio AI] Runtime=Docker  Profile=%PROFILE%
docker compose -f compose.ai.yml run --rm medallio-ai run --profile "%PROFILE%"
exit /b %ERRORLEVEL%

:local
echo [Medallio AI] Docker no disponible o modo local forzado. Usando .venv...
if not exist ".venv\Scripts\python.exe" (
  echo [Medallio AI] ERROR: no existe .venv\Scripts\python.exe
  echo Ejecuta primero scripts\01_instalar.bat
  exit /b 10
)
".venv\Scripts\python.exe" ".\scripts\medallio_ai_runtime.py" run --profile "%PROFILE%"
exit /b %ERRORLEVEL%
