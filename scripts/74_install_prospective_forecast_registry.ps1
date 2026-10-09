$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.8.3..."
    & $Python -m py_compile `
        ".\scripts\forecast_evaluation_v28.py" `
        ".\scripts\medallio_predictive_gate_v28.py" `
        ".\scripts\medallio_evidence_outcome_v27.py" `
        ".\scripts\medallio_ambassador_v2.py" `
        ".\scripts\install_v283_prospective_registry.py"

    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.8.3" }

    Write-Host "[2/3] Instalando Prospective Registry + Maturity Clock + Naive Benchmark..."
    & $Python ".\scripts\install_v283_prospective_registry.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v2.8.3" }

    Write-Host "[3/3] Status..."
    & $Python ".\scripts\forecast_evaluation_v28.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status v2.8.3" }
}
finally {
    Pop-Location
}
