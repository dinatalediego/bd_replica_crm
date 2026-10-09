$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.9.2.1..."
    & $Python -m py_compile ".\scripts\project_milestones_deadline_policy_v2921.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.9.2.1" }

    Write-Host "[2/3] Instalando milestones + deadline policy..."
    & $Python ".\scripts\project_milestones_deadline_policy_v2921.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación v2.9.2.1" }

    Write-Host "[3/3] Estado..."
    & $Python ".\scripts\project_milestones_deadline_policy_v2921.py" status
    if ($LASTEXITCODE -ne 0) { throw "Falló status v2.9.2.1" }

    Write-Host ""
    Write-Host "IMPORTANTE:"
    Write-Host "- Las fechas de entrega permanecen PRELIMINARY."
    Write-Host "- Las recomendaciones NO aprueban ni activan contratos."
    Write-Host "- Revisa MD/MT approval_template.json y confirma manualmente los campos."
}
finally {
    Pop-Location
}
