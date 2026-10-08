$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "Medallio OS" -ForegroundColor Cyan
Write-Host "Repo: $repo"
& $python -m streamlit run "apps\medallio_os\app.py"
