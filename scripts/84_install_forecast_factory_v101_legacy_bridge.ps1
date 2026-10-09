$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/4] Compilando Forecast Factory v1.0.1..."
    & $Python -m py_compile ".\scripts\forecast_factory_v101_legacy_bridge.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v1.0.1" }

    Write-Host "[2/4] Aplicando horizon semantics + honest intervals..."
    & $Python ".\scripts\forecast_factory_v101_legacy_bridge.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v1.0.1" }

    Write-Host "[3/4] Bridging commercial_forecasting legacy evidence..."
    & $Python ".\scripts\forecast_factory_v101_legacy_bridge.py" bridge
    if ($LASTEXITCODE -ne 0) { throw "Falló bridge v1.0.1" }

    Write-Host "[4/4] Estado..."
    & $Python ".\scripts\forecast_factory_v101_legacy_bridge.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status v1.0.1" }

    Write-Host ""
    Write-Host "IMPORTANTE:"
    Write-Host "- No se inventan intervalos cuando faltan errores maduros."
    Write-Host "- El forecast legado queda marcado CUMULATIVE_WINDOW."
    Write-Host "- mean3 es el benchmark naive del bridge."
    Write-Host "- SHADOW nunca se presenta como evidencia prospectiva defendible."
}
finally {
    Pop-Location
}
