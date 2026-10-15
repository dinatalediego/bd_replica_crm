# Medallio v2.8.3 — Prospective Forecast Registry + Maturity Clock + Benchmark Naïve

## El cambio conceptual

v2.8.2.1 demostró que el histórico disponible era principalmente:

```text
BACKTEST_ONLY
UNVERIFIED
```

y que no existía evidencia verificable de forecasts emitidos antes del outcome.

v2.8.3 deja de intentar "rescatar" retrospectivamente esa evidencia.
Desde la instalación empieza a fabricar evidencia prospectiva limpia.

## 1. Prospective Forecast Registry

Nuevos objetos:

```text
model_control.forecast_issue_batch
model_control.forecast_issue_registry
model_control.v_forecast_issue_canonical
```

Cada forecast emitido por Ambassador conserva:

```text
issue_id
issue_batch_id
issued_at
slot
project_key
origin_period
target_period
horizon
prediction
model_name
model_version
source_run_id
stock_at_issue
```

### Regla de inmutabilidad

Una emisión nunca se sobrescribe.

Si el forecast cambia:

```text
08-oct → 7 unidades
20-oct → 9 unidades
```

existen dos revisiones.

Si el forecast NO cambia, no se crea una copia artificial en cada correo.
El batch registra `unchanged_rows`.

### Dry run

```text
--dry-run
```

NO emite forecasts nuevos.
Sólo consulta el estado actual.

## 2. Maturity Clock

```text
analytics.v_forecast_maturity_clock_v283
model_control.forecast_maturity_event
analytics.refresh_forecast_maturity_v283()
```

Estados:

```text
INCUBATING
EVALUATED
OVERDUE_NO_ACTUAL
```

Una predicción sólo pasa a `EVALUATED` cuando:

```text
target month < mes actual
AND mes_parcial = false
AND ventas_mes IS NOT NULL
```

El evento de madurez queda persistido una sola vez.

## 3. Benchmark naïve congelado al emitir

```text
model_control.forecast_naive_benchmark_snapshot
```

Medallio calcula en el momento de la emisión:

```text
ROLLING_3M_MEAN
LAST_COMPLETE_MONTH
SEASONAL_12M
```

Política primaria:

```text
Rolling 3M
↓ fallback
Último mes completo
↓ fallback
Mismo mes -12M
```

El benchmark también queda congelado.
No se recalcula usando información futura.

## 4. Evaluación modelo vs naïve

```text
analytics.v_forecast_evaluation_v283
analytics.v_forecast_performance_v283
analytics.v_forecast_defensible_v283
```

Además de WAPE y Bias se calculan:

```text
naive_wape_pct
skill_vs_naive_pct
model_beat_rate_pct
benchmark_coverage_pct
```

`skill_vs_naive_pct > 0` significa que el modelo reduce error frente al benchmark.

## 5. Gate L3 v2.8.3

```text
analytics.v_forecast_predictive_gate_v283
```

PASS exige:

```text
>= 12 outcomes maduros
>= 3 proyectos
>= 3 celdas defendibles
WAPE <= 25%
|Bias| <= 15%
benchmark coverage >= 90%
skill vs naïve > 0
beat rate >= 50%
100% leakage-safe
```

Medallio no puede obtener PASS sólo por tener un WAPE aceptable:
también debe demostrar que agrega valor frente a una regla sencilla.

## 6. Predictive Evidence Factory

```text
analytics.v_predictive_evidence_factory_v283
```

El CEO puede ver:

```text
Emitidos
Celdas activas
Revisiones
Incubando
Evaluados
Overdue
Próxima madurez
Benchmark coverage
Model WAPE
Naive WAPE
Skill vs naïve
```

## 7. Nueva slide CEO

Se añade una octava slide:

```text
Predictive Evidence Factory · emisión → madurez → benchmark
```

Antes de que existan outcomes maduros, la slide enseña progreso real:

```text
Emitidos       84
Incubando      84
Evaluados       0
Próxima madurez 2026-12-01
Skill vs naïve N/A
```

## 8. Artifacts

```text
forecast_issue_registry_current.csv
forecast_maturity_clock.csv
forecast_naive_benchmarks.csv
forecast_factory_summary.json
06_predictive_evidence_factory.png
```

## Instalación

Copiar el ZIP sobre:

```text
C:\Projects\bd_replica_crm
```

y ejecutar:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\74_install_prospective_forecast_registry.ps1
```

La instalación realiza una primera emisión prospectiva real.

## Validación

```powershell
python .\scripts\forecast_evaluation_v28.py status
```

Después:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

El dry-run no altera el registry.

Finalmente:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

Si los forecasts no cambiaron desde la instalación es normal ver:

```text
inserted=0
unchanged=84
```

Eso demuestra idempotencia, no un error.
