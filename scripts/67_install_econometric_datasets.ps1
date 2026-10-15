param([switch]$StandaloneTask)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$schemaPath = Join-Path $projectRoot 'scripts\schema_sync.py'
$refreshPath = Join-Path $projectRoot 'scripts\econometric_datasets.py'
if (-not (Test-Path $pythonPath)) { throw 'Instalar .venv y pip install -e . antes de continuar.' }
Push-Location $projectRoot
try {
    & $pythonPath $schemaPath --only absorcion_ventas_mensual --only evolucion_comercial --only econometric_datasets
    if ($LASTEXITCODE -ne 0) { throw 'Falló instalación de contratos SQL.' }
    & $pythonPath $refreshPath refresh --backfill
    if ($LASTEXITCODE -ne 0) { throw 'Falló reconstrucción inicial. No se registra tarea.' }
    if ($StandaloneTask) {
        $action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$refreshPath`" refresh --once-per-day" -WorkingDirectory $projectRoot
        $trigger = New-ScheduledTaskTrigger -Daily -At '10:15'
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName 'Medallio - Datasets Econometricos' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Captura local diaria y actualización econométrica; sin consultas Redshift.' -Force
        Get-ScheduledTask -TaskName 'Medallio - Datasets Econometricos'
    } else {
        Write-Host 'Instalado. El paso 07b del dw_refresh horario ejecutará la captura una vez por día.'
        Write-Host 'Verifique que su tarea activa llame scripts\run_hourly.bat de este repositorio.'
    }
} finally { Pop-Location }
