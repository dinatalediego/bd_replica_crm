$TaskName = "Medallio - Replica Redshift Local"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Tarea eliminada: $TaskName"
