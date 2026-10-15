$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) { throw "No existe $Python" }

Push-Location $Root
try {
    Write-Host "[1/3] Compilando Forecast Factory Contract v1..."
    & $Python -m py_compile ".\scripts\forecast_factory_contract_v1.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación Forecast Factory Contract v1" }

    Write-Host "[2/3] Instalando contrato canónico..."
    & $Python ".\scripts\forecast_factory_contract_v1.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación Forecast Factory Contract v1" }

    Write-Host "[3/3] Estado..."
    & $Python ".\scripts\forecast_factory_contract_v1.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status Forecast Factory Contract v1" }

    Write-Host ""
    Write-Host "Forecast Factory Contract v1 instalado."
    Write-Host "Todo modelo futuro debe escribir el contrato canónico antes de llegar a Power BI."
}
finally {
    Pop-Location
}
