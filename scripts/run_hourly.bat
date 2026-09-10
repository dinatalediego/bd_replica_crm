@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 10

rem Punto unico de mantenimiento del DW.
rem La tarea de Windows sigue apuntando a este archivo; toda la orquestacion vive en Python.
call ".venv\Scripts\python.exe" ".\scripts\dw_refresh.py" --mode hourly
exit /b %ERRORLEVEL%
