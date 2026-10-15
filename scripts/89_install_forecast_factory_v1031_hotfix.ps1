$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/4] Compilando v1.0.3.1 hotfix..."
    & $Python -m py_compile ".\scripts\forecast_factory_v103.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v1.0.3.1" }

    Write-Host "[2/4] Instalando schema corregido v1.0.3.1..."
    & $Python ".\scripts\forecast_factory_v103.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación schema v1.0.3.1" }

    Write-Host "[3/4] Ejecutando maturity cycle..."
    & $Python ".\scripts\forecast_factory_v103.py" run-cycle --trigger-source MANUAL
    if ($LASTEXITCODE -ne 0) { throw "Falló maturity cycle v1.0.3.1" }

    Write-Host "[4/4] Validando estado..."
    & $Python ".\scripts\forecast_factory_v103.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status v1.0.3.1" }

    Write-Host ""
    Write-Host "v1.0.3.1 HOTFIX OK."
    Write-Host "- Corregida columna duplicada model_name/model_version/model_family."
    Write-Host "- Evidence Calendar y CEO Evidence Status ya pueden crearse."
}
finally {
    Pop-Location
}
