param(
    [string]$RepoRoot = "C:\Projects\bd_replica_crm",
    [string]$Morning = "08:00",
    [string]$Midday = "13:00",
    [string]$Evening = "18:30"
)

$ErrorActionPreference = "Stop"

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Script = Join-Path $RepoRoot "scripts\medallio_ambassador_v2.py"

if (!(Test-Path $Python)) { throw "No existe $Python" }
if (!(Test-Path $Script)) { throw "No existe $Script" }

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$tasks = @(
    @{Name="Medallio Ambassador v2 - Morning"; Slot="morning"; Time=$Morning},
    @{Name="Medallio Ambassador v2 - Midday"; Slot="midday"; Time=$Midday},
    @{Name="Medallio Ambassador v2 - Evening"; Slot="evening"; Time=$Evening}
)

foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction `
        -Execute $Python `
        -Argument "`"$Script`" --slot $($t.Slot)" `
        -WorkingDirectory $RepoRoot

    $trigger = New-ScheduledTaskTrigger -Daily -At $t.Time

    Register-ScheduledTask `
        -TaskName $t.Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Medallio Enterprise Ambassador v2" `
        -Force | Out-Null

    Write-Host "OK: $($t.Name) @ $($t.Time)"
}
