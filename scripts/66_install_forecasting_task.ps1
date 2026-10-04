# Installs a task for the current Windows user, without password or administrator credentials.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path $projectRoot 'scripts\commercial_forecasting.py'
if (-not (Test-Path $pythonPath)) { throw 'Instalar .venv antes de registrar la tarea.' }
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$scriptPath`" run --once-per-month" -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At '09:15'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName 'Medallio - Forecasting Comercial Mensual' -Action $action -Trigger $trigger -Settings $settings -Description 'Entrena una vez por mes cerrado con PostgreSQL local; conserva predicciones y errores.' -Force
