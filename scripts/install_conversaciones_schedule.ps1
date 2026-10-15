param(
    [string[]]$Hours = @('09:00', '15:00', '21:00')
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$runner = Join-Path $PSScriptRoot 'check_conversaciones_scheduled.py'
$source = Join-Path $root 'conversaciones\Chat de WhatsApp con Cygnus - Ventas.txt'
$taskName = 'Medallio - Conversaciones Cygnus Ventas'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Falta Python: $python" }
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Falta el TXT: $source" }
if ($Hours.Count -ne 3 -or @($Hours | Select-Object -Unique).Count -ne 3) {
    throw 'Indica exactamente tres horarios diferentes en formato HH:mm.'
}

# Ensure the local database contract is ready before registering the task.
& $python (Join-Path $PSScriptRoot 'schema_sync.py') --only conversaciones
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación del esquema; no se creó la tarea.' }

$culture = [System.Globalization.CultureInfo]::InvariantCulture
$triggers = @($Hours | ForEach-Object {
    $at = [datetime]::ParseExact($_, 'HH:mm', $culture)
    New-ScheduledTaskTrigger -Daily -At $at
})
$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}"' -f $runner) -WorkingDirectory $root
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "Tarea instalada: $taskName"
Write-Host "Usuario: $user; zona horaria de Windows: $((Get-TimeZone).Id)"
Write-Host "Horarios locales: $($Hours -join ', ')"
Write-Host "Log privado: $(Join-Path $root 'conversaciones\scheduler_runs.jsonl')"
