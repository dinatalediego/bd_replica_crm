$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.9.3.2..."
    & $Python -m py_compile ".\scripts\current_state_semantics_v2932.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.9.3.2" }

    Write-Host "[2/3] Aplicando current-state semantics..."
    & $Python ".\scripts\current_state_semantics_v2932.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v2.9.3.2" }

    Write-Host "[3/3] Validando..."
    & $Python ".\scripts\current_state_semantics_v2932.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló validación v2.9.3.2" }

    Write-Host ""
    Write-Host "Objetivo:"
    Write-Host "- Mantener historia CANCELLED."
    Write-Host "- Excluir historia cancelada de KPIs/issues operativos."
    Write-Host "- CEO Control Tower usa solo la intervención vigente por proyecto."
}
finally {
    Pop-Location
}
