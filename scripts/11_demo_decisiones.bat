@echo off
cd /d "%~dp0\.."
.venv\Scripts\python.exe -m replica_cygnus.cli decision-demo
