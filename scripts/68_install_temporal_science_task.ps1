param(
    [string]$At = '10:45',
    [switch]$SkipInitialRun
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path $projectRoot 'scripts\temporal_science.py'
if (-not (Test-Path $pythonPath)) { throw 'Instalar .venv y pip install -e . antes de continuar.' }
if (-not (Test-Path $scriptPath)) { throw 'No se encuentra scripts\temporal_science.py.' }

Push-Location $projectRoot
try {
    & $pythonPath $scriptPath init
    if ($LASTEXITCODE -ne 0) { throw 'Falló instalación del control plane temporal.' }

    if (-not $SkipInitialRun) {
        & $pythonPath $scriptPath run
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'La instalación SQL quedó aplicada, pero el primer ciclo no terminó completamente. Revise status antes de programar.'
            & $pythonPath $scriptPath status
            throw 'Primer ciclo temporal incompleto; no se registra la tarea todavía.'
        }
    }

    $action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$scriptPath`" run --once-per-day" -WorkingDirectory $projectRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName 'Medallio - Temporal Science Factory' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Perfiles temporales, suitability, micro probability y forecasting macro local; no consulta Redshift directamente.' -Force
    Get-ScheduledTask -TaskName 'Medallio - Temporal Science Factory'
    Write-Host 'Tarea instalada. Usa datos locales de Medallio y respeta los locks/idempotencia del forecasting existente.'
} finally {
    Pop-Location
}
