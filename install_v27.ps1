param(
    [string]$RepoRoot = "C:\Projects\bd_replica_crm",
    [switch]$ApplySchema
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) { throw "No existe $Python" }

Write-Host "[v2.7] Validando módulos..."
& $Python -m py_compile `
    ".\scripts\medallio_evidence_outcome_v27.py" `
    ".\scripts\medallio_ambassador_v2.py" `
    ".\scripts\apply_v27_evidence_outcome_schema.py"

if ($ApplySchema) {
    Write-Host "[v2.7] Aplicando schema Evidence & Outcome..."
    & $Python ".\scripts\apply_v27_evidence_outcome_schema.py"
}

Write-Host ""
Write-Host "Prueba recomendada:"
Write-Host 'python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run'
