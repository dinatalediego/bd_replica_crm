$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.9.2..."
    & $Python -m py_compile ".\scripts\contract_activation_v292.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Falló compilación v2.9.2"
    }

    Write-Host "[2/3] Instalando Human Approval + Contract Activation + Outcome SLA..."
    & $Python ".\scripts\contract_activation_v292.py" install
    if ($LASTEXITCODE -ne 0) {
        throw "Falló instalación v2.9.2"
    }

    Write-Host "[3/3] Estado..."
    & $Python ".\scripts\contract_activation_v292.py" status
    if ($LASTEXITCODE -ne 0) {
        throw "Falló status v2.9.2"
    }

    Write-Host ""
    Write-Host "IMPORTANTE: instalación NO aprueba ni activa contratos."
    Write-Host "Completa primero los approval_template.json de MD y/o MT."
}
finally {
    Pop-Location
}
