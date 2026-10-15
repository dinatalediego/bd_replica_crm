$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Push-Location $Root
try {
    Write-Host "[1/2] Compilando hotfix v2.8.2.1..."
    & $Python -m py_compile `
        ".\scripts\forecast_evaluation_v28.py" `
        ".\scripts\medallio_evidence_outcome_v27.py" `
        ".\scripts\medallio_predictive_gate_v28.py" `
        ".\scripts\medallio_ambassador_v2.py" `
        ".\scripts\calibrate_predictive_evidence_v2821.py"

    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.8.2.1" }

    Write-Host "[2/2] Aplicando calibración compatible..."
    & $Python ".\scripts\calibrate_predictive_evidence_v2821.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló calibración v2.8.2.1" }
}
finally {
    Pop-Location
}
