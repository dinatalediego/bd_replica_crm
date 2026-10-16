param(
    [ValidateSet("Install", "Remove")]
    [string]$Mode = "Install",
    [int]$FirstRunMinutes = 15
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $ProjectRoot "scripts\RUN_MEDALLIO_AI.bat"
$TaskName = "Medallio - AI Runtime"

if ($Mode -eq "Remove") {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Tarea eliminada: $TaskName"
    } else {
        Write-Host "La tarea no existe: $TaskName"
    }
    exit 0
}

if (-not (Test-Path $Runner)) {
    throw "No se encontro el runner: $Runner"
}

$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$Runner`" auto" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes($FirstRunMinutes) `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Medallio AI: scoring horario, ciencia temporal diaria y challenger semanal. Docker si esta disponible; fallback a .venv. Sin auto-promocion de modelos." `
    -Force | Out-Null

Write-Host "Tarea creada/actualizada: $TaskName"
Write-Host "Primera ejecucion en aproximadamente $FirstRunMinutes minutos; luego cada hora."
Write-Host "El perfil auto decide que jobs hourly/daily/weekly estan vencidos."
