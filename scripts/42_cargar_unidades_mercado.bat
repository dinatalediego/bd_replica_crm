@echo off
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
  echo Uso: %~nx0 RUTA_ARCHIVO SOURCE_ID [FECHA_SNAPSHOT]
  exit /b 2
)
if "%~2"=="" (
  echo Uso: %~nx0 RUTA_ARCHIVO SOURCE_ID [FECHA_SNAPSHOT]
  exit /b 2
)

if "%~3"=="" (
  call ".venv\Scripts\python.exe" -m mercado_ingestion.cli load --file "%~1" --source-id "%~2"
) else (
  call ".venv\Scripts\python.exe" -m mercado_ingestion.cli load --file "%~1" --source-id "%~2" --snapshot-date "%~3"
)
exit /b %ERRORLEVEL%

