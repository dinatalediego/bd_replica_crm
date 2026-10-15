$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.9.3..."
    & $Python -m py_compile ".\scripts\intervention_ledger_v293.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.9.3" }

    Write-Host "[2/3] Instalando Action Execution Evidence + Intervention Ledger..."
    & $Python ".\scripts\intervention_ledger_v293.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v2.9.3" }

    Write-Host "[3/3] Estado..."
    & $Python ".\scripts\intervention_ledger_v293.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status v2.9.3" }

    Write-Host ""
    Write-Host "IMPORTANTE:"
    Write-Host "- MD y MT se crean como SCHEDULED, no STARTED."
    Write-Host "- Registrar STARTED sólo cuando la acción realmente comience."
    Write-Host "- Execution evidence y Outcome evidence son capas separadas."
}
finally {
    Pop-Location
}
