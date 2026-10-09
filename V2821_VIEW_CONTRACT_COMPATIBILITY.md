# Medallio v2.8.2.1 — PostgreSQL View Contract Compatibility

## Error corregido

PostgreSQL lanzó:

```text
no se puede cambiar el nombre de la columna «run_id» de la vista a «evidence_class»
```

La causa no era un dato incorrecto.

`CREATE OR REPLACE VIEW` conserva el contrato posicional de una vista existente.
v2.8.2 intentaba insertar:

```text
evidence_class
selection_evidence
```

antes de `run_id`, por lo que PostgreSQL interpretó que se estaba renombrando
la quinta columna existente.

La misma incompatibilidad habría ocurrido después en
`analytics.v_forecast_predictive_gate`, porque v2.8.2 también cambiaba
el orden de las columnas públicas del gate.

## Qué hace v2.8.2.1

No usa `DROP VIEW ... CASCADE`.

Preserva exactamente el prefijo de columnas ya publicado y añade
las nuevas columnas únicamente al final.

También corrige un detalle adicional:
`mature_pairs` se calcula como la suma real de pares maduros por
proyecto×horizonte, no como el número de celdas de performance.

## Seguridad

El script ejecuta un preflight contra `information_schema.columns`.

Si el contrato real de tu base no coincide con el esperado, aborta
antes de modificar las vistas.

El intento fallido anterior estaba dentro de `BEGIN ... COMMIT`,
por lo que PostgreSQL revirtió ese bloque y no dejó una calibración parcial.

## Instalación

Copiar el ZIP sobre:

```text
C:\Projects\bd_replica_crm
```

y ejecutar:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\73_fix_v282_view_compat.ps1
```

No repite el backfill y no borra los snapshots existentes.

Después:

```powershell
python .\scripts\forecast_evaluation_v28.py status
```

y luego:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```
