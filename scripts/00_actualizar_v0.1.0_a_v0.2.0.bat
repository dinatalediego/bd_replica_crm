@echo off
setlocal
cd /d "%~dp0.."

echo ==============================================
echo Actualizacion Replica Redshift Local v0.2.0
echo ==============================================
echo.
echo Este script NO elimina .env ni config\tables.yml.
echo Actualizara dependencias y creara decision_systems.yml si no existe.
echo.

call scripts\01_instalar.bat
if errorlevel 1 (
  echo ERROR: La actualizacion de dependencias fallo.
  exit /b 1
)

echo.
echo PATCH INSTALADO.
echo Siguiente paso, con PostgreSQL local activo:
echo   scripts\03_inicializar_postgres.bat
echo   scripts\10_validar_contratos_decision.bat
echo   scripts\11_demo_decisiones.bat
endlocal
