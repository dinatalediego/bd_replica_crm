$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.8.2..."
    & $Python -m py_compile `
        ".\scripts\forecast_evaluation_v28.py" `
        ".\scripts\medallio_evidence_outcome_v27.py" `
        ".\scripts\medallio_predictive_gate_v28.py" `
        ".\scripts\medallio_ambassador_v2.py"

    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.8.2" }

    Write-Host "[2/3] Calibrando evidencia predictiva..."
    & $Python ".\scripts\calibrate_predictive_evidence_v282.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló calibración v2.8.2" }

    Write-Host "[3/3] Status final..."
    & $Python ".\scripts\forecast_evaluation_v28.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status predictivo" }
}
finally {
    Pop-Location
}
