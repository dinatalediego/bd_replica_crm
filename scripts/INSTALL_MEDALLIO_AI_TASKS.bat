@echo off
setlocal
cd /d "%~dp0.."

set "MODE=Install"
if /I "%~1"=="remove" set "MODE=Remove"

powershell -NoProfile -File ".\scripts\install_medallio_ai_tasks.ps1" -Mode "%MODE%"
exit /b %ERRORLEVEL%
