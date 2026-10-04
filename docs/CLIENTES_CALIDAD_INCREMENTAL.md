# Clientes calidad: incremental local

`02b_clientes_calidad_refresh` vuelve a ejecutar el mismo contrato DQ desde
`dw_refresh.py`, después de RAW/schema y antes de portal/CORE. No consulta Redshift.

## Comportamiento

- Compara `source_id` y un MD5 del JSON de origen, excluyendo solamente
  `_etl_loaded_at` y `_etl_source_run_id` (metadatos verificados de la réplica).
- Escanea RAW local para detectar diferencias; transforma únicamente altas/cambios.
  No es CDC: la detección sigue siendo O(n) sobre PostgreSQL local.
- Reemplaza solo esas identidades mediante DELETE/INSERT dentro de una transacción.
  El resto conserva `refreshed_at`. Las bajas se eliminan si ya no existen en RAW;
  no descubre eliminaciones en Redshift que la réplica RAW no haya propagado.
- Primera ejecución, cambio de definición DQ o `--full`: un recálculo completo
  sin TRUNCATE. El hash de las definiciones del procedimiento y normalizador
  invalida las reglas previas. La segunda ejecución sin cambios transforma cero.
- Conserva prioridad celulares/celular/teléfono, validación extranjera, DNI,
  score y todos los campos existentes. CTEs materializadas evitan expandir
  repetidamente las expresiones de normalización.
- IDs RAW nulos, vacíos o duplicados bloquean el refresh sin modificar staging.
  El gate SQL compara identidad/hash y conteo; el gate Python se evalúa antes
  de confirmar la transacción. Una falla detiene el pipeline, no reporta OK.
- Lock transaccional rechaza otro refresh DQ. Locks de tablas estabilizan RAW
  y serializan escrituras en staging; las lecturas continúan. El script espera
  hasta 30 segundos por locks y hasta 900 segundos por sentencia (configurable).

## Actualizar desde VS Code (PowerShell)

Usar el commit de esta entrega sobre la rama local, conservando las reparaciones
locales de portal, configuración y orquestador. No hacer reset/checkout forzado.

```powershell
cd C:\Projects\bd_replica_crm
git status --short
git fetch origin
# Usar el hash exacto publicado en el PR/entrega:
git cherry-pick <commit-clientes-calidad>
```

Si hay cambios locales en archivos de esta entrega, Git frenará el cherry-pick:
conservarlos antes de resolver, sin descartar el arreglo de portal. La entrega
no cambia `refresh_portal_conversion.py`, `config/tables.yml`, ni `dw_refresh.py`.

Para validar sin solapamiento, esperar a que la tarea esté Ready. Deshabilitar
solo el trigger durante la prueba; no detener una ejecución en progreso.

```powershell
$TaskName = 'Medallio - Replica Redshift Local'
if ((Get-ScheduledTask -TaskName $TaskName).State -eq 'Running') {
    throw 'Esperar a que termine la tarea actual.'
}
Disable-ScheduledTask -TaskName $TaskName

.\.venv\Scripts\python.exe .\scripts\schema_sync.py --only clientes_calidad
if ($LASTEXITCODE -ne 0) { throw 'Fallo instalando el componente DQ.' }

.\.venv\Scripts\python.exe .\scripts\refresh_clientes_calidad.py
if ($LASTEXITCODE -ne 0) { throw 'Fallo el primer refresh DQ.' }

.\.venv\Scripts\python.exe .\scripts\refresh_clientes_calidad.py
if ($LASTEXITCODE -ne 0) { throw 'Fallo la comprobacion incremental.' }

.\.venv\Scripts\python.exe .\scripts\enable_clientes_calidad_step.py
if ($LASTEXITCODE -ne 0) { throw 'Revisar el bloque temporal 02b.' }

.\.venv\Scripts\python.exe .\scripts\dw_refresh.py --mode manual --local-only
if ($LASTEXITCODE -ne 0) { throw 'Resolver el FAIL antes de habilitar Windows.' }

Enable-ScheduledTask -TaskName $TaskName
```

El helper habilita únicamente el bloque comentado conocido de 02b, valida AST,
respalda `dw_refresh.py` y conserva el resto. Si 02b ya está activo, no escribe.
Si encuentra un formato distinto o un archivo contaminado, frena para revisión.
Si alguna validación falla, el trigger queda deshabilitado para resolver la falla;
no declarar la automatización restaurada todavía.

## Evidencia de operación

La consola muestra `mode`, `source_rows`, `inserted_rows`, `updated_rows`,
`deleted_rows`, `unchanged_rows` y `duration`. Primera corrida: `rebuild`.
Segunda sin cambios: `incremental`, inserted/updated/deleted=0.

```sql
SELECT *, finished_at - started_at AS duration
FROM staging.clientes_calidad_refresh_runs
ORDER BY run_id DESC LIMIT 10;

SELECT * FROM staging.v_clientes_calidad_health;
```

Los runs contienen métricas agregadas, sin PII. En la corrida completa buscar
`OK 02b_clientes_calidad_refresh` y `DW_REFRESH_OK`. La siguiente ejecución
Windows debe terminar con `LastTaskResult=0`.

## Validación

Pruebas de contrato y activación; pruebas PostgreSQL desechables de cambios,
no-op, metadatos, bajas, migración, invalidación de reglas, DQ, rollback del gate
Python y concurrencia. `CLIENTES_CALIDAD_TEST_DSN`/`ABSORCION_TEST_DSN` deben
apuntar exclusivamente a una BD desechable: las fixtures rechazan esquemas ocupados.
Las mediciones sintéticas no predicen la duración en la PC del usuario.
