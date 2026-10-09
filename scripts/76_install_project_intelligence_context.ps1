$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    Write-Host "[1/3] Compilando v2.9.0..."
    & $Python -m py_compile `
        ".\scripts\project_intelligence_context_v290.py" `
        ".\scripts\project_ai_synthesis_v290.py"

    if ($LASTEXITCODE -ne 0) {
        throw "Falló compilación v2.9.0"
    }

    Write-Host "[2/3] Instalando Project Intelligence Context..."
    & $Python ".\scripts\project_intelligence_context_v290.py" install
    if ($LASTEXITCODE -ne 0) {
        throw "Falló schema v2.9.0"
    }

    Write-Host "[3/3] Compilando contexto de todos los proyectos..."
    & $Python ".\scripts\project_intelligence_context_v290.py" refresh
    if ($LASTEXITCODE -ne 0) {
        throw "Falló refresh de contexto v2.9.0"
    }

    Write-Host ""
    & $Python ".\scripts\project_intelligence_context_v290.py" status
}
finally {
    Pop-Location
}
