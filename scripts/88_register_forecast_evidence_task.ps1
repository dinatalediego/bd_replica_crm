param(
    [string]$TaskName = "Medallio - Forecast Evidence Cycle",
    [string]$At = "06:15"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$RunScript = Join-Path $Root "scripts\87_run_forecast_evidence_cycle.ps1"

if (!(Test-Path $RunScript)) {
    throw "No existe $RunScript"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""

$Trigger = New-ScheduledTaskTrigger -Daily -At $At

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Medallio Forecast Factory v1.0.3: refresh actuals, mature evidence and update model scoreboard." `
    -Force

Write-Host "Task registrada: $TaskName"
Write-Host "Frecuencia: diaria a las $At"
Write-Host "Script: $RunScript"
