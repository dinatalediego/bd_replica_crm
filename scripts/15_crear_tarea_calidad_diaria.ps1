$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $ProjectRoot "scripts\14_calidad_profunda_no_pause.bat"
$TaskName = "Medallio - Data Quality Profunda"

$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Runner`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:30"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Ejecuta reconciliacion y calidad profunda diaria para Medallio Control Tower." -Force
Write-Host "Tarea creada: $TaskName (diaria 06:30)"
