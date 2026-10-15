# Medallio v2.8 — Forecast Evaluation & Predictive Gate

## Objetivo

L3 deja de preguntar:

> ¿Existe un modelo de forecast?

y pasa a preguntar:

> ¿Existen predicciones emitidas antes del outcome y comparables contra meses completos reales?

La cadena queda:

```text
forecast emitido
→ snapshot congelado
→ target month
→ mes comercial completo
→ actual
→ error
→ WAPE / Bias
→ proyecto × horizonte
→ Predictive Gate
→ CEO slide
```

## 1. Histórico de forecasts emitidos

Se crea:

```text
model_control.forecast_prediction_snapshot
```

Campos principales:

```text
project_key
origin_period
target_period
horizon
prediction
issued_at
issuance_evidence
leakage_safe
run_id
model_name
model_version
```

La instalación intenta backfill desde:

```text
analytics.commercial_forecast_predictions
analytics.commercial_forecast_backtest
features.commercial_forecast_snapshots
```

El mapping de columnas es dinámico.

Además, cada corrida de Ambassador congela el forecast vigente desde:

```text
analytics.v_commercial_forecast_current
```

Por ello, incluso si el histórico anterior es incompleto, Medallio empezará desde ahora a fabricar una historia prospectiva limpia.

## 2. Matching con outcomes maduros

Se crea:

```text
analytics.v_forecast_evaluation_mature
```

Un forecast sólo entra cuando:

1. `target_period` está antes del mes actual de Lima;
2. `analytics.comercial_proyecto_mes.mes_parcial = false`;
3. existe `ventas_mes`;
4. el forecast fue emitido antes de iniciar el target month;
5. la predicción estaba seleccionada/champion cuando existe esa bandera.

El mes actual nunca entra al WAPE.

## 3. Performance por proyecto × horizonte

```text
analytics.v_forecast_performance_by_project_horizon
```

Calcula:

```text
mature_pairs
WAPE
Bias
MAE
RMSE
MAPE
leakage_safe_pct
distinct_runs
```

Una celda es `DEFENSIBLE` cuando:

```text
n >= 3
WAPE <= 25%
|Bias| <= 15%
leakage_safe = 100%
```

## 4. Gate L3

```text
analytics.v_forecast_predictive_gate
```

PASS exige:

```text
mature_pairs >= 12
projects_with_mature >= 3
defensible_cells >= 3
global WAPE <= 25%
|global Bias| <= 15%
leakage_safe = 100%
```

Con menor evidencia queda `WARN` o `BLOCK`.

No se fuerza L3.

## 5. Nueva slide CEO

Ambassador agrega una séptima slide:

# Predicciones que ya podemos defender

Incluye:

```text
Gate L3
Pares maduros
Proyectos cubiertos
WAPE
Bias

DEFENDIBLES
Proyecto · Horizonte · n · WAPE · Bias

NO PROMOVER TODAVÍA
WATCH / INSUFFICIENT
```

La política del gate queda visible al pie.

## 6. Artifacts

```text
forecast_predictive_gate.json
forecast_performance_project_horizon.csv
forecast_defensible.csv
05_ceo_defensible_forecasts.png
```

## Instalación

Copiar sobre:

```text
C:\Projects\bd_replica_crm
```

y ejecutar:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\70_install_forecast_predictive_gate.ps1
```

Luego:

```powershell
python .\scripts\forecast_evaluation_v28.py status
```

Después:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

y finalmente:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

## Resultado esperado

Es totalmente correcto obtener:

```text
L1 PASS
L2 PASS
L3 BLOCK
```

si el backfill no contiene suficientes forecasts realmente emitidos antes del outcome.

El valor de v2.8 es que ese bloqueo ya queda cuantificado:

```text
cuántos pares maduros faltan
qué proyectos tienen evidencia
qué horizontes funcionan
qué WAPE existe
qué Bias existe
qué celdas ya son defendibles
```

Eso convierte L3 en una meta verificable y no en una declaración tecnológica.
