param(
    [ValidateSet("install","refresh","status")]
    [string]$Command = "install"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python. Activa/instala el venv primero."
}

Push-Location $Root
try {
    Write-Host "[1/2] Validando contratos previos..."
    & $Python scripts\schema_sync.py --status
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "schema_sync reporta componentes pendientes; se continuará sólo si los objetos requeridos existen."
    }

    Write-Host "[2/2] Project Growth State..."
    & $Python scripts\project_growth_state.py $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Falló project_growth_state.py"
    }
}
finally {
    Pop-Location
}
