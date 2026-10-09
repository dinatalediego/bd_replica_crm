$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.9.3.1..."
    & $Python -m py_compile ".\scripts\monitoring_semantics_v2931.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.9.3.1" }

    Write-Host "[2/3] Aplicando Monitoring Semantics..."
    & $Python ".\scripts\monitoring_semantics_v2931.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v2.9.3.1" }

    Write-Host "[3/3] Validando..."
    & $Python ".\scripts\monitoring_semantics_v2931.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló validación v2.9.3.1" }

    Write-Host ""
    Write-Host "IMPORTANTE:"
    Write-Host "- SCHEDULED/STARTED/IMPLEMENTED => outcome_phase=NOT_STARTED."
    Write-Host "- WAITING_OUTCOME comienza al completar ejecución."
    Write-Host "- Si una primary_metric es compuesta, NO iniciar ese contrato."
}
finally {
    Pop-Location
}
