$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/4] Compilando Forecast Factory v1.0.3..."
    & $Python -m py_compile ".\scripts\forecast_factory_v103.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v1.0.3" }

    Write-Host "[2/4] Instalando Evidence Calendar + Scoreboard..."
    & $Python ".\scripts\forecast_factory_v103.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v1.0.3" }

    Write-Host "[3/4] Ejecutando primer maturity cycle..."
    & $Python ".\scripts\forecast_factory_v103.py" run-cycle --trigger-source MANUAL
    if ($LASTEXITCODE -ne 0) { throw "Falló primer maturity cycle v1.0.3" }

    Write-Host "[4/4] Estado final..."
    & $Python ".\scripts\forecast_factory_v103.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status v1.0.3" }

    Write-Host ""
    Write-Host "v1.0.3 instalado."
    Write-Host "- Evidence Calendar activo."
    Write-Host "- Maturity evaluator idempotente."
    Write-Host "- Scoreboard exige amplitud temporal antes de recomendar promoción."
    Write-Host "- Champion nunca se declara automáticamente."
}
finally {
    Pop-Location
}
