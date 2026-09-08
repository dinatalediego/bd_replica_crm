# Power BI — Decision Intelligence semantic layer

Esta capa mueve la lógica pesada al PostgreSQL local (`medallio_dw`) y deja Power BI como capa de presentación, filtros, medidas ligeras y storytelling.

## Instalación

Desde la raíz del repositorio:

```powershell
python scripts/install_powerbi_decision_intelligence.py
```

El instalador crea/actualiza vistas y funciones de `analytics` y valida que el catálogo quede completo.

## Objetos de Power BI

| Orden | Objeto | Grano | Página recomendada |
|---:|---|---|---|
| 1 | `analytics.v_pbi_di_executive` | 1 fila | Executive Decision Intelligence |
| 2 | `analytics.v_pbi_policy_funnel` | etapa | Funnel operativo |
| 3 | `analytics.v_pbi_policy_capacity` | fecha × experimento × proyecto × banda | Policy & Capacity |
| 4 | `analytics.v_pbi_policy_adoption` | fecha × policy × asesor × banda | Adoption / SLA |
| 5 | `analytics.v_pbi_experiment_performance` | experimento × outcome | Experiment / Causal Impact |
| 6 | `analytics.v_pbi_advisor_execution` | fecha × asesor × proyecto × banda | Commercial Execution |
| 7 | `analytics.v_pbi_model_monitoring` | semana × modelo × proyecto × banda | Model Monitoring |
| 8 | `analytics.v_pbi_economic_value` | experimento | Economic Value |
| 9 | `analytics.v_pbi_policy_journey` | recomendación | Drillthrough / auditoría |
| 10 | `analytics.v_pbi_policy_registry` | experimento/policy | Dimensión policy |

`analytics.v_pbi_di_catalog` documenta el catálogo desde SQL.

## Página 1 — Executive Decision Intelligence

Fuente principal: `analytics.v_pbi_di_executive`.

Cards sugeridas:

- `serving_scores_n`
- `eligible_current_n`
- `assigned_n`
- `recommendations_n`
- `actions_n`
- `adoption_rate`
- `within_sla_rate`
- `sep_rate`
- `minuta_rate`
- `primary_outcome_itt_pp`
- `next_bottleneck`

El objetivo de esta página es responder: **¿la predicción está llegando a una acción y esa acción ya tiene evidencia de resultado?**

## Página 2 — Policy & Capacity

Fuentes:

- `analytics.v_pbi_policy_funnel`
- `analytics.v_pbi_policy_capacity`

Visuales sugeridos:

1. Pipeline horizontal con `stage_label`, `stage_rows`, `conversion_from_prior`.
2. Capacidad vs asignados por día.
3. Treatment vs Control por proyecto.
4. Distribución por `priority_band`.
5. Utilización diaria: `capacity_utilization_day`.

La vista default usa `lead_priority_v2` y lookback de 7 días. Para otros parámetros existe:

```sql
SELECT *
FROM analytics.fn_pbi_policy_funnel('lead_priority_v2', 14);
```

## Página 3 — Experiment / Causal Impact

Fuente: `analytics.v_pbi_experiment_performance`.

Visual principal:

- `treatment_rate`
- `control_rate`
- `itt_difference_pp`
- `relative_lift`
- `treatment_maturity_rate`
- `control_maturity_rate`
- `experiment_evidence_status`
- `control_contamination_flag`

No presentar `itt_difference_pp` como evidencia concluyente cuando `experiment_evidence_status <> 'READY_FOR_ITT_REVIEW'`.

## Página 4 — Commercial Execution

Fuente: `analytics.v_pbi_advisor_execution`.

Visuales sugeridos:

- matriz asesor × proyecto;
- scatter `adoption_rate` vs `minuta_rate`;
- bubble size = `recommendations`;
- SLA por asesor;
- mediana de minutos a acción.

Esto permite separar problemas de modelo de problemas de ejecución comercial.

## Página 5 — Model & Policy Monitoring

Fuente: `analytics.v_pbi_model_monitoring`.

Visuales sugeridos:

- score P10/P50/P90 por semana;
- mix A/B/C/D;
- predicted vs actual separation;
- predicted vs actual minuta;
- `sep_calibration_gap_pp`;
- `minuta_calibration_gap_pp`;
- filtros por `model_version`, proyecto y `is_serving`.

## Página 6 — Economic Value

Fuente: `analytics.v_pbi_economic_value`.

Campos protegidos:

- `estimated_incremental_primary_outcomes_on_matured_treatment`
- `estimated_incremental_realized_value`
- `estimated_net_incremental_value`
- `estimated_incremental_roi`
- `economic_value_status`

Los campos monetarios incrementales permanecen `NULL` hasta que Treatment y Control tengan outcomes maduros y `realized_value` esté completo. Esto evita etiquetar valor observado como valor causal.

## Drillthrough

Fuente: `analytics.v_pbi_policy_journey`.

Un registro representa una recomendación. La vista preserva:

```text
evidence_key
→ score_id / model_run_id
→ policy_id / experiment_id / treatment_group
→ recommendation_id
→ action_id / SLA / costo
→ separacion_14d / minuta_60d
→ realized_value
```

Para imports incrementales o parámetros de fecha/proyecto se puede usar:

```sql
SELECT *
FROM analytics.fn_pbi_decision_window(
    DATE '2026-08-01',
    DATE '2026-09-30',
    'lead_priority_v2',
    NULL
);
```

## Modelo semántico recomendado

Evitar relacionar entre sí todas las vistas agregadas como si fueran dimensiones. Tratarlas como facts de presentación con dimensiones compartidas en Power BI:

- Fecha
- Policy
- Proyecto
- Asesor
- Modelo
- Experimento

`v_pbi_policy_registry` puede funcionar como dimensión de Policy/Experimento. La tabla calendario puede mantenerse como dimensión DAX o migrarse más adelante al DW si se desea estandarizarla.

## Regla de arquitectura

```text
PostgreSQL / medallio_dw
    lógica de negocio
    policy
    causal readiness
    agregaciones
    lineage
        ↓
Power BI
    visualización
    filtros
    medidas ligeras
    narrativa ejecutiva
```

No reconstruir en Power Query la lógica ya publicada por estas vistas.
