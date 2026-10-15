$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.9.3.1.1..."
    & $Python -m py_compile ".\scripts\monitoring_semantics_v2931.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.9.3.1.1" }

    Write-Host "[2/3] Aplicando hotfix de compatibilidad de vistas..."
    & $Python ".\scripts\monitoring_semantics_v2931.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló hotfix v2.9.3.1.1" }

    Write-Host "[3/3] Validando..."
    & $Python ".\scripts\monitoring_semantics_v2931.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló validación v2.9.3.1.1" }

    Write-Host ""
    Write-Host "Hotfix aplicado:"
    Write-Host "- Se preservó el contrato de columnas de las vistas v2.9.3."
    Write-Host "- Nuevas columnas semánticas se agregaron al final."
    Write-Host "- SCHEDULED debe mostrar outcome_phase=NOT_STARTED."
}
finally {
    Pop-Location
}
