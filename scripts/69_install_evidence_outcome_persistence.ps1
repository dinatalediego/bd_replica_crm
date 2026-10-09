$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    & $Python ".\scripts\install_v275_persistence.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Falló instalación de persistence ledgers."
    }

    Write-Host ""
    Write-Host "Validando runtime..."
    & $Python ".\scripts\validate_v274_runtime_reliability.py"
}
finally {
    Pop-Location
}
