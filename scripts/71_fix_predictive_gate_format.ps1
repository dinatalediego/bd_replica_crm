$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    Write-Host "[1/2] Aplicando hotfix SQL v2.8.1..."
    & $Python ".\scripts\fix_v281_predictive_gate_format.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Falló fix_v281_predictive_gate_format.py"
    }

    Write-Host ""
    Write-Host "[2/2] Revalidando Predictive Gate..."
    & $Python ".\scripts\forecast_evaluation_v28.py" status
    if ($LASTEXITCODE -ne 0) {
        throw "Falló status v2.8"
    }
}
finally {
    Pop-Location
}
