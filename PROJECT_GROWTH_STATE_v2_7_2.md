# Medallio v2.7.2 — Project Growth State + Governed CEO Actions

## Objetivo

Mover L2 de `WARN` a `PASS` con un contrato comparable real por proyecto.

No se fuerza el gate. El gate pasa únicamente si:

```text
analytics.v_project_growth_state
```

devuelve filas con proyecto + métricas reales comparables.

## Fuentes

### Operación física
`analytics.comercial_proyecto_mes`

- stock lanzamiento
- stock inicial/final
- ventas
- absorción
- mes de vida
- unidades en revisión

Rolling 3m/6m usa exclusivamente meses completos.

### Forecast
`analytics.v_commercial_forecast_current`
`analytics.v_commercial_forecast_performance`

- forecast H1
- shortfall
- WAPE por proyecto sólo sobre outcomes elegibles/maduros

### Economics
`decision_intelligence.v_ml_impact_baseline`

- meta
- colocado
- gap
- stock monetario
- cumplimiento
- conciliación

Los escenarios +5/+10/+20 **no se convierten en Value to Capture**.

### Pricing
`analytics.v_comercial_indice_precios`

Sólo observaciones reales; no hay imputación.

## CEO Decision Queue

Se crean:

```text
decision_intelligence.v_project_growth_actions
decision_intelligence.v_ceo_growth_decision_queue
```

La cola deja de depender de:

```text
Mantener rumbo y exigir evidencia de valor
```

como única acción.

### Acción transversal incorporada

Mientras no existan outcomes maduros:

> Hacer obligatorio capturar outcome y ROI de cada decisión asistida por IA.

Owner:

```text
AI Steering Committee
```

Nivel:

```text
D1_RECOMMEND
```

Luego se priorizan acciones por proyecto según:

- gap a meta
- meses hasta stock cero
- shortfall forecast
- unidades en revisión
- conciliación económica

## Outcome y ROI

Toda acción generada lleva:

```text
outcome_required = true
roi_required = true
suggested_outcome_metric
```

Esto toma la recomendación actual del board y la convierte en un control operativo.

## Instalación

En el repo:

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -e .
powershell -ExecutionPolicy Bypass -File .\scripts\68_project_growth_state.ps1 -Command install
```

Después:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

Esperado si la vista devuelve proyectos:

```text
L1 OBSERVED       PASS
L2 DIAGNOSTIC     PASS
```

L3 puede continuar BLOCK por WAPE. Eso es correcto.

## Validación rápida

```sql
SELECT
  project_key,
  project_name,
  stock_units,
  last_complete_sales_units,
  absorption_rate,
  months_to_zero,
  gap_value,
  forecast_units,
  forecast_wape_pct,
  attention_score,
  suggested_action
FROM analytics.v_project_growth_state
ORDER BY attention_score DESC;
```

Y:

```sql
SELECT *
FROM decision_intelligence.v_ceo_growth_decision_queue
LIMIT 10;
```
