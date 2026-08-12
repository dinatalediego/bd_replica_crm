@echo off
setlocal
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0\15_crear_tarea_calidad_diaria.ps1"
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
