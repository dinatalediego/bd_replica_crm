$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Push-Location $Root
try {
    Write-Host "[1/2] Compilando v2.8.4..."
    & $Python -m py_compile ".\scripts\pre_maturity_control_v284.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.8.4" }

    Write-Host "[2/2] Instalando control pre-madurez + execution loop..."
    & $Python ".\scripts\pre_maturity_control_v284.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló v2.8.4" }
}
finally { Pop-Location }
