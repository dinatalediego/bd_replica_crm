param(
    [string]$RepoRoot = "C:\Projects\bd_replica_crm",
    [string]$Morning = "08:00",
    [string]$Midday = "13:00",
    [string]$Evening = "18:30"
)

$ErrorActionPreference = "Stop"

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Script = Join-Path $RepoRoot "scripts\medallio_ambassador\run_ambassador.py"

if (!(Test-Path $Python)) {
    throw "No existe Python del venv: $Python"
}
if (!(Test-Path $Script)) {
    throw "No existe Ambassador: $Script"
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$tasks = @(
    @{ Name="Medallio Ambassador - Morning"; Slot="morning"; Time=$Morning },
    @{ Name="Medallio Ambassador - Midday"; Slot="midday"; Time=$Midday },
    @{ Name="Medallio Ambassador - Evening"; Slot="evening"; Time=$Evening }
)

foreach ($t in $tasks) {
    $arguments = "`"$Script`" --slot $($t.Slot)"
    $action = New-ScheduledTaskAction `
        -Execute $Python `
        -Argument $arguments `
        -WorkingDirectory $RepoRoot

    $trigger = New-ScheduledTaskTrigger -Daily -At $t.Time

    Register-ScheduledTask `
        -TaskName $t.Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Ejecuta Medallio notebooks, prioriza artefactos ejecutivos y envía briefing Gmail." `
        -Force | Out-Null

    Write-Host "OK: $($t.Name) a las $($t.Time)"
}

Write-Host ""
Write-Host "Tareas registradas."
Write-Host "Prueba una manualmente con:"
Write-Host "Start-ScheduledTask -TaskName 'Medallio Ambassador - Morning'"
