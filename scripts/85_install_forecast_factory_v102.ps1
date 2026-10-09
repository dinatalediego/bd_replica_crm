$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/5] Compilando Forecast Factory v1.0.2..."
    & $Python -m py_compile ".\scripts\forecast_factory_v102.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v1.0.2" }

    Write-Host "[2/5] Instalando Prospective Clock + Lead-Time schema..."
    & $Python ".\scripts\forecast_factory_v102.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v1.0.2" }

    Write-Host "[3/5] Derivando monthly increments..."
    & $Python ".\scripts\forecast_factory_v102.py" adapt-monthly
    if ($LASTEXITCODE -ne 0) { throw "Falló Monthly Increment Adapter" }

    Write-Host "[4/5] Cargando actuals cerrados + scope compatibility..."
    & $Python ".\scripts\forecast_factory_v102.py" load-actuals
    if ($LASTEXITCODE -ne 0) { throw "Falló Actual Loader" }

    Write-Host "[5/5] Estado..."
    & $Python ".\scripts\forecast_factory_v102.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status v1.0.2" }

    Write-Host ""
    Write-Host "v1.0.2 instalado."
    Write-Host "- Cumulative windows -> monthly increments."
    Write-Host "- Future target months can become strict PROSPECTIVE evidence."
    Write-Host "- Closed actual months are loaded automatically."
    Write-Host "- Existing-stock scope is evaluated conservatively."
    Write-Host "- Lead-time WAPE/Bias/Skill is ready when outcomes mature."
}
finally {
    Pop-Location
}
