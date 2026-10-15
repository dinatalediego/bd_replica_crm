$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
    throw "No existe $Python"
}

Push-Location $Root
try {
    Write-Host "[1/4] Compilando v2.9.0 evidence-ceiling fix + v2.9.1..."
    & $Python -m py_compile `
        ".\scripts\project_intelligence_context_v290.py" `
        ".\scripts\project_ai_analyst_v291.py"
    if ($LASTEXITCODE -ne 0) { throw "Falló compilación v2.9.1" }

    Write-Host "[2/4] Refrescando contexto con evidence ceiling corregido..."
    & $Python ".\scripts\project_intelligence_context_v290.py" refresh
    if ($LASTEXITCODE -ne 0) { throw "Falló refresh v2.9.0 corregido" }

    Write-Host "[3/4] Instalando AI Project Analyst + Decision Contract Drafts..."
    & $Python ".\scripts\project_ai_analyst_v291.py" install
    if ($LASTEXITCODE -ne 0) { throw "Falló schema v2.9.1" }

    Write-Host "[4/4] Analizando portfolio activo..."
    & $Python ".\scripts\project_ai_analyst_v291.py" refresh
    if ($LASTEXITCODE -ne 0) { throw "Falló refresh v2.9.1" }

    Write-Host ""
    & $Python ".\scripts\project_ai_analyst_v291.py" status
}
finally {
    Pop-Location
}
