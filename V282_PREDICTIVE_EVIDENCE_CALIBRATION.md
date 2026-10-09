# Medallio v2.8.2 — Predictive Evidence Calibration

## Por qué existe

v2.8.1 reveló:

```text
mature_pairs = 19,430
projects = 14
defensible_cells = 0
WAPE ≈ 333.4%
Bias ≈ +307.4%
```

Eso NO debe interpretarse todavía como "el forecast real de Medallio tiene 333% de error".

Es una señal de auditoría.

Las causas posibles incluyen:

- backtests retrospectivos mezclados con forecasts realmente emitidos;
- timestamps derivados del origin en vez de evidencia real de emisión;
- varias predicciones/modelos por la misma celda proyecto×origen×horizonte;
- diferencia de escala/grano entre `prediction` y `ventas_mes`.

## Corrección de gobierno

La evidencia queda separada en:

```text
PROSPECTIVE_ISSUED
HISTORICAL_ISSUED
BACKTEST_ONLY
UNVERIFIED
```

Sólo las dos primeras pueden promover L3.

`BACKTEST_ONLY` sirve para diagnóstico y model development,
pero no para afirmar que Medallio "predijo antes de conocer la realidad".

## Leakage estricto

Para scoring operacional:

```text
issuance_evidence = SOURCE_CREATED_AT
issued_at < target_period
```

`DERIVED_FROM_ORIGIN` ya NO cuenta como prueba de emisión.

## Canonicalización

Se elige una sola predicción por:

```text
project
origin
target
horizon
```

tomando la última predicción realmente emitida antes del target.

## Gate corregido

PASS:

```text
>= 12 pares operacionales maduros
>= 3 proyectos
>= 3 celdas defendibles
WAPE <= 25%
|Bias| <= 15%
100% leakage-safe
```

WARN:

```text
>= 6 pares
>= 2 proyectos
>= 1 celda defendible
WAPE <= 50%
|Bias| <= 30%
100% leakage-safe
```

Si WAPE > 50% o |Bias| > 30%, el gate permanece BLOCK
aunque existan miles de observaciones.

## Nuevos artifacts

```text
forecast_source_diagnostic.csv
forecast_evidence_audit.csv
```

Permiten contestar:

- qué fuente está produciendo el error;
- qué evidencia es backtest;
- cuántas filas existen por celda;
- si prediction y actual parecen estar en escalas distintas.

## Instalar

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\72_calibrate_predictive_evidence.ps1
```

No borra snapshots ni repite el backfill.

Después:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

y, cuando el resultado sea coherente:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```
