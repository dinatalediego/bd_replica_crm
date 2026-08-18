# Runbook — primera decisión real end-to-end

## Objetivo

Convertir el ciclo comercial certificado de MEDALLIO en una cola accionable de separaciones con riesgo de caída, preservando identidad, snapshot, explicación, feedback y outcome.

```text
core.fact_ciclo_comercial_unidad
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

## Prerrequisito de rama

El PR del Decision Engine nació antes de que el CORE comercial y el lifecycle fueran certificados. Antes de validar localmente esta rama, incorporar `main` para disponer de:

- `core.dim_proyecto`;
- `core.dim_unidad`;
- `core.fact_ciclo_comercial_unidad`;
- pipeline horario reconciliado.

## 1. Instalar el módulo

Desde la raíz del repositorio:

```powershell
python -m pip install -e ".\decision_engine[dev]"
```

## 2. Instalar el runtime y publicar features

Ya no es necesario pegar SQL manualmente en DBeaver:

```powershell
python -m cygnus_decision_engine --env-file .env install-separation-risk
```

El comando instala en orden:

1. `decision_engine/sql/00_decision_control.sql`;
2. `decision_engine/sql/02_separation_fall_risk_features.sql`;
3. `decision_engine/sql/01_separation_fall_risk_runtime.sql`.

## 3. Validar el feature contract

```powershell
python -m cygnus_decision_engine --env-file .env validate-separation-risk
```

El gate falla si existen candidatos duplicados, `BLOCKED` o sin `observed_at`.

### Semántica v0.1 de features

La identidad y el estado comercial sí son certificados: provienen de `core.fact_ciclo_comercial_unidad` y solo se consideran ciclos `ABIERTA` cuya separación fuente sigue `Activo`.

Dos señales permanecen deliberadamente provisionales y se exponen como `WARN`, no se ocultan:

- `interaction_count_14d`: proxy binario 0/1 construido con la última interacción conocida por cliente+proyecto. El baseline actual solo distingue cero vs no-cero;
- `has_pending_admin_block`: `NULL` hasta certificar la regla administrativa. El baseline lo trata como `False`, pero `admin_signal_mode='NOT_YET_CERTIFIED'` queda trazado en el snapshot.

Estas limitaciones permiten probar el circuito operativo sin fingir una madurez de features que todavía no existe.

## 4. Prueba sin escritura

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --dry-run --top 20
```

Debe producir una lista ordenada por riesgo con acciones:

- `urgent_follow_up`;
- `follow_up`;
- `monitor`.

## 5. Persistir la primera corrida

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --top 20
```

La escritura es idempotente para:

`decision_key + entity_type + entity_id + observed_at + policy_version`.

Ejecutar dos veces sobre el mismo snapshot no debe duplicar recomendaciones.

## 6. Consumir la cola comercial

```sql
select *
from decision_intelligence.v_separation_fall_risk_worklist
order by action_priority, score desc nulls last, separation_id;
```

La worklist expone directamente proyecto, unidad, proforma, documento, asesor y señales del baseline desde `feature_snapshot`, evitando depender de joins posteriores contra RAW mutable.

## 7. Cerrar el feedback loop

Cuando la recomendación se muestre, acepte, modifique o rechace, registrar un evento en `decision_intelligence.recommendation_feedback`.

Cuando se conozca el desenlace, registrar en `decision_intelligence.recommendation_outcome`, por ejemplo `fell_before_sale=true` o `converted_to_sale=true`, junto con valor económico cuando pueda calcularse.

## Definition of Done

La primera decisión se considera operativa cuando:

- el feature contract nace del lifecycle certificado;
- el gate devuelve 0 candidatos `BLOCKED`;
- el dry-run genera una priorización legible;
- dos ejecuciones del mismo snapshot no duplican recomendaciones;
- la cola puede consultarse desde SQL/Power BI;
- al menos una recomendación puede enlazarse a feedback humano y outcome;
- existe un corte semanal para comparar `urgent_follow_up` vs caída/venta observada.

## Próxima mejora de feature quality

Antes de entrenar ML, sustituir los dos proxies v0.1 por:

1. conteo exacto de interacciones point-in-time 7/14/30 días;
2. regla certificada de bloqueo administrativo.

El baseline v0.1 seguirá siendo el benchmark que el primer modelo supervisado deberá superar out-of-time.
