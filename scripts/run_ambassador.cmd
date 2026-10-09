@echo off
setlocal
cd /d C:\Projects\bd_replica_crm
".venv\Scripts\python.exe" "scripts\medallio_ambassador\run_ambassador.py" --slot %1
endlocal
