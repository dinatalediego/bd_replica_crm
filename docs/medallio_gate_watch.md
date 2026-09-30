# Medallio: gateway y Watch

Única tarea: `Medallio - Replica Redshift Local`, en bd_replica_crm. Órbita consume PostgreSQL; mantener `Orbita - Medallio` deshabilitada.

El maestro despierta cada hora. El comando `sync --due-only` consulta el último éxito **por tabla** en `etl_control.sync_state` antes de abrir Redshift. Incrementales: 4 horas; full_refresh: 24 horas. Configurables en `.env`: `REDSHIFT_SYNC_INTERVAL_HOURS=4`, `REDSHIFT_FULL_SYNC_INTERVAL_HOURS=24`. No cambia llaves, ventanas de lookback ni watermarks. Sin éxito previo se considera vencida. Estado futuro no genera consultas hasta alcanzar su intervalo.

Fuentes de `config/tables.yml` más `config/hourly_required_tables.yml` se reúnen en una sesión Redshift (salvo reconexión ante fallo transitorio). La configuración local gana sobre duplicados, incluso si deshabilita una fuente. Un lock PostgreSQL impide sincronizadores Gate simultáneos. Los comandos `sync` anteriores siguen siendo manuales sin Gate: no programarlos como una segunda tarea.

`watch` lee exclusivamente PostgreSQL y muestra fuente, réplica exitosa, edad, intervalo efectivo, watermark replicado, filas, último intento y error. No necesita credenciales Redshift. La edad es tiempo desde réplica; no es atraso medido contra la fuente actual. Los fallos de conexión anteriores a iniciar una tabla están en `logs/replica.log` y `logs/dw_refresh.log`. El procesamiento local queda registrado en `dw_refresh.log` (`DW_REFRESH_OK`, START/OK/FAIL por capa), no se confunde con frescura RAW.

El maestro reemplaza `observe` por `watch`. El antiguo `observe` sigue siendo un diagnóstico explícito que **consulta Redshift**, con sus SLAs históricos; no usarlo como monitor horario ni habilitar una tarea diaria profunda sin revisar su coste.

## Prueba local antes de reactivar

En PowerShell desde el repositorio:

```powershell
 git pull --ff-only origin feat/medallio-redshift-gate-watch
 .\.venv\Scripts\python.exe -m replica_cygnus.cli watch --additional-config config/hourly_required_tables.yml
 .\.venv\Scripts\python.exe .\scripts\dw_refresh.py --local-only
```

`--local-only` omite la sincronización RAW y ejecuta las capas locales existentes. No incorpora fuentes deshabilitadas ni garantiza que datos antiguos sean recientes. El fallo de una capa se propaga y el Watch corre en finally. Una sincronización fallida sigue bloqueando la promoción automática de capas posteriores.

Tras comprobar el ciclo local, ejecutar una corrida controlada (puede consultar Redshift y recuperar el intervalo pendiente):

```powershell
 .\scripts\run_hourly.bat
 .\.venv\Scripts\python.exe -m replica_cygnus.cli watch --additional-config config/hourly_required_tables.yml
```

Si no hay fallos, en PowerShell con permisos para administrar tareas:

```powershell
 .\scripts\07_crear_tarea_horaria.ps1
 Get-ScheduledTask -TaskName 'Orbita - Medallio','Medallio - Replica Redshift Local' | Select-Object TaskName, State
```

El instalador reemplaza la tarea canónica, activa la frecuencia horaria y programa su primera ejecución en 2 minutos. No ejecutarlo antes de verificar la corrida controlada. No se han validado las conexiones ni las transformaciones de tu Windows desde el entorno de desarrollo. El problema de metadata de Redshift puede seguir bloqueando una tabla y necesita diagnóstico separado si reaparece.
