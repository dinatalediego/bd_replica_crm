$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.8..."
    & $Python -m py_compile `
        ".\scripts\forecast_evaluation_v28.py" `
        ".\scripts\medallio_predictive_gate_v28.py" `
        ".\scripts\medallio_evidence_outcome_v27.py" `
        ".\scripts\medallio_ambassador_v2.py"

    if ($LASTEXITCODE -ne 0) {
        throw "Falló compilación de v2.8"
    }

    Write-Host "[2/3] Instalando + backfill histórico..."
    & $Python ".\scripts\install_v28_predictive_gate.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Falló install_v28_predictive_gate.py"
    }

    Write-Host "[3/3] Status..."
    & $Python ".\scripts\forecast_evaluation_v28.py" status
}
finally {
    Pop-Location
}
