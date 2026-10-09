$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

$LogDir = Join-Path $Root "logs\forecast_factory"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "forecast_evidence_cycle_$Stamp.log"

Push-Location $Root
try {
    "[$(Get-Date -Format o)] Forecast evidence cycle start" | Tee-Object -FilePath $LogFile

    & $Python ".\scripts\forecast_factory_v103.py" run-cycle `
        --trigger-source TASK_SCHEDULER 2>&1 |
        Tee-Object -FilePath $LogFile -Append

    if ($LASTEXITCODE -ne 0) {
        throw "Forecast evidence cycle falló. Revisar $LogFile"
    }

    "[$(Get-Date -Format o)] Forecast evidence cycle OK" |
        Tee-Object -FilePath $LogFile -Append
}
finally {
    Pop-Location
}
