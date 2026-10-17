$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $ProjectRoot "scripts\run_hourly.bat"
$TaskName = "Medallio - Replica Redshift Local"

$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Runner`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 90)

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $Action `
  -Trigger $Trigger `
  -Settings $Settings `
  -Description "Sincroniza Redshift hacia PostgreSQL y mantiene Medallio: Gate por tabla (incremental 4h, full refresh 24h), marts locales y evolucion comercial al menos una vez al dia." `
  -Force

Write-Host "Tarea creada: $TaskName"
Write-Host "La primera ejecucion sera aproximadamente en 2 minutos y luego cada hora durante 10 anos."
Write-Host "El limite por corrida es 90 minutos; MultipleInstances=IgnoreNew evita solapamientos."
