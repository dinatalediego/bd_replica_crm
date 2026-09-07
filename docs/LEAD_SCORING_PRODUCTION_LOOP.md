# Lead Scoring v0.1 — ciclo challenger controlado

## Objetivo
Cerrar el primer loop ML real de `priorizacion_leads`:

`clientes_proyectos -> evidencia -> labels -> features point-in-time -> challenger -> gate -> serving/champion -> score diario -> outcomes`.

El score es de **propensión**, no de persuadibilidad causal. Ordena atención comercial; todavía no afirma que contactar al lead cause la conversión.

## Targets y score
- `p_separacion_14d`: probabilidad de separación dentro de 14 días.
- `p_minuta_60d`: probabilidad de minuta/venta validada dentro de 60 días.
- `priority_score = 100 * (0.55*p_sep + 0.45*p_minuta)`.

Los pesos son configurables y provisionales.

## Evidencia
`features.lead_evidence` conserva una fila por `lead_id + fecha_asignacion`. El documento del cliente se usa solo para vincular outcomes; no se usa como feature predictiva.

El backfill histórico se marca `BACKFILL_INFERRED`; desde la puesta en marcha, la captura diaria queda `LIVE`. Esto es importante porque una fuente operacional podría sobrescribir una asignación histórica.

Los labels usan el ciclo certificado `core.fact_ciclo_comercial_unidad`: `fecha_separacion` y `fecha_venta`. Las tasas históricas solo usan outcomes cuyo horizonte ya había madurado antes del `decision_at` de la fila actual, evitando leakage.

## Challenger y promoción
El entrenamiento utiliza división temporal; nunca random split. Cada entrenamiento queda en `model_control.model_runs` como `CHALLENGER` junto con artifact URI, features, ventanas, Git SHA y métricas.

El gate evalúa simultáneamente AUC, Brier, conversiones reales del top 20%, tamaño de muestra y positivos. El primer modelo que supera el baseline se habilita como `PROVISIONAL serving`, no como champion. Los challengers posteriores que pasan quedan `PASS_FOR_REVIEW` y no reemplazan automáticamente al modelo actual.

Promoción explícita:

```powershell
python scripts/lead_scoring.py promote --model-run-id <UUID> --approved-by "<nombre>"
```

Eso mueve los aliases `champion` y `serving` y deja evidencia en `model_control.model_promotions`.

## Primer ciclo

```powershell
.\scripts\40_lead_scoring_first_cycle.bat
```

Operación diaria, sin reentrenar:

```powershell
.\scripts\41_lead_scoring_live.bat
```

Entrenar challenger posterior:

```powershell
.\scripts\42_lead_scoring_train_challenger.bat
```

Estado:

```powershell
.\scripts\43_lead_scoring_status.bat
```

## Power BI
Ranking vigente:

```sql
SELECT *
FROM decision_intelligence.v_lead_priority_current
ORDER BY decision_date DESC, priority_rank;
```

Performance una vez maduran outcomes:

```sql
SELECT *
FROM decision_intelligence.v_lead_score_matured_performance
ORDER BY model_version, priority_band;
```

La señal de negocio esperada es que la banda A madure con mayor tasa de separación y minuta que B/C/D. Eso complementa AUC/Brier con una métrica directamente interpretable para operación comercial.

## De score a acción y outcome (v0.2)

El ciclo diario también materializa recomendaciones y outcomes maduros. La acción
humana se registra explícitamente y puede analizarse en Power BI. Ver
`docs/LEAD_ACTION_OUTCOME_LOOP.md`.

## Definition of Done
El loop se considera cerrado cuando PostgreSQL puede demostrar: evidencia de qué se sabía al llegar el lead, target posterior, features sin leakage, challenger reproducible, test temporal, gate auditado, alias serving, scores diarios versionados y performance real por banda cuando maduren outcomes.

## Limitaciones conscientes v0.1
- `fecha_asignacion` es la marca temporal de decisión y debe validarse contra el comportamiento real de Sperant.
- El asesor/canal/medio se resuelve entre nombres de columnas candidatos y queda registrado en `feature_payload`.
- Drift se registra como `NOT_EVALUATED_V0`; será la siguiente capa de monitoreo.
- Artifacts son locales y quedan fuera de Git; luego pueden migrar a object storage sin cambiar el contrato lógico.
