# Runbook — primera decisión real end-to-end

## Objetivo

Convertir un snapshot reconciliado de separaciones activas en una cola diaria de acciones comerciales, preservando trazabilidad y feedback.

```text
analytics reconciliado
        ↓
features.separation_fall_risk_current
        ↓
quality gate
        ↓
baseline separation_fall_risk
        ↓
decision_intelligence.recommendation
        ↓
v_separation_fall_risk_worklist
        ↓
asesor / supervisor
        ↓
recommendation_feedback
        ↓
recommendation_outcome
```

## 1. Instalar el módulo

Desde la raíz del repositorio:

```powershell
python -m pip install -e ".\decision_engine[dev]"
```

## 2. Crear tablas de control

En PostgreSQL local, ejecutar en orden:

```text
decision_engine/sql/00_decision_control.sql
decision_engine/sql/01_separation_fall_risk_runtime.sql
```

## 3. Publicar el feature contract

El runtime exige la relación `features.separation_fall_risk_current`.

No se crea desde RAW automáticamente. Debe provenir del ciclo comercial reconciliado y contener:

- `separation_id`
- `observed_at`
- `days_since_separation`
- `days_since_last_interaction`
- `interaction_count_14d`
- `has_pending_admin_block`
- `quality_status`
- `quality_reasons`

Si una identidad/ciclo no es confiable, usar `quality_status='BLOCKED'`; el motor devuelve `do_not_decide`.

## 4. Prueba sin escritura

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --dry-run --top 20
```

## 5. Persistir la corrida

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --top 20
```

La escritura es idempotente para `decision_key + entity_type + entity_id + observed_at + policy_version`.

## 6. Consumir la cola comercial

```sql
select *
from decision_intelligence.v_separation_fall_risk_worklist
order by action_priority, score desc nulls last, separation_id;
```

Prioridad: `urgent_follow_up`, `follow_up`, `monitor`.

## 7. Cerrar el feedback loop

Cuando la recomendación se muestre, acepte, modifique o rechace, registrar un evento en `decision_intelligence.recommendation_feedback`.

Cuando se conozca el desenlace, registrar en `decision_intelligence.recommendation_outcome`, por ejemplo `fell_before_sale=true` o `converted_to_sale=true`, junto con valor económico cuando pueda calcularse.

## Definition of Done

La primera decisión se considera operativa cuando:

- el feature contract se genera con datos point-in-time;
- ningún caso `BLOCKED` llega a la cola activa;
- dos ejecuciones del mismo snapshot no duplican recomendaciones;
- la cola puede consultarse desde SQL/Power BI;
- al menos una recomendación puede enlazarse a feedback humano y outcome;
- existe un corte semanal para comparar `urgent_follow_up` vs caída/venta observada.
