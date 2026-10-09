# Medallio v2.8.1 — PostgreSQL `format()` hotfix

## Qué pasó

La instalación v2.8 llegó correctamente a:

```text
schema: OK
historical snapshot generation: OK
current freeze: OK
```

La falla ocurrió sólo al consultar:

```text
analytics.v_forecast_predictive_gate
```

PostgreSQL `format()` NO usa sintaxis printf como:

```sql
%.1f
```

Sólo reconoce principalmente:

```text
%s
%I
%L
%%
```

Por eso expresiones como:

```sql
format('WAPE global maduro %.1f%% ...', global_wape_pct)
```

producían:

```text
psycopg.errors.InvalidParameterValue:
especificador de tipo no reconocido
```

## Corrección

v2.8.1 reemplaza esos textos por `concat()` + `round()`:

```sql
concat(
    'WAPE global maduro ',
    round(global_wape_pct, 1),
    '% supera el umbral CEO de 25%.'
)
```

También se corrige Bias y leakage-safe.

## Importante

NO necesitas repetir el backfill histórico completo.

Los snapshots creados antes del error permanecen en:

```text
model_control.forecast_prediction_snapshot
```

Este hotfix sólo reemplaza la vista del gate.

## Instalar

Copiar el ZIP sobre:

```text
C:\Projects\bd_replica_crm
```

y ejecutar:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\71_fix_predictive_gate_format.ps1
```

Debe mostrar inmediatamente:

```text
snapshots=...
mature_evaluable_rows=...
gate=BLOCK/WARN/PASS
pairs=...
projects=...
defensible_cells=...
WAPE=...
Bias=...
reason=...
```

Después:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

y finalmente:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```
