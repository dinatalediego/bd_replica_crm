@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0\07_crear_tarea_horaria.ps1"
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
