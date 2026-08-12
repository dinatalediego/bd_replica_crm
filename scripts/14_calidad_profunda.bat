@echo off
setlocal
cd /d "%~dp0.."
echo ADVERTENCIA: este modo realiza COUNT(*) y controles de duplicados.
echo Se recomienda fuera de horas de alta carga y no cada hora.
call ".venv\Scripts\python.exe" -m replica_cygnus.cli observe --mode deep
set CODE=%ERRORLEVEL%
pause
exit /b %CODE%
