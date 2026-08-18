# Runbook — primera decisión real end-to-end

## Objetivo

Convertir el ciclo comercial certificado de MEDALLIO en una cola accionable de separaciones con riesgo de caída, preservando identidad, snapshot, explicación, feedback y outcome.

```text
core.fact_ciclo_comercial_unidad
        ↓
universo ABIERTA + Activo
        ↓
proforma first-seen dentro de 3 meses calendario
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
```

## Prerrequisito

La rama debe incorporar `main` para disponer de `core.dim_proyecto`, `core.dim_unidad`, `core.fact_ciclo_comercial_unidad` y el pipeline horario reconciliado.

## 1. Instalar el módulo

```powershell
python -m pip install -e ".\decision_engine[dev]"
```

## 2. Instalar runtime y publicar features

```powershell
python -m cygnus_decision_engine --env-file .env install-separation-risk
```

Instala, en orden:

1. `decision_engine/sql/00_decision_control.sql`;
2. `decision_engine/sql/02_separation_fall_risk_features.sql`;
3. `decision_engine/sql/01_separation_fall_risk_runtime.sql`.

## 3. Regla de elegibilidad de proforma

Antes del scoring se construye `features.v_separation_fall_risk_candidate_universe`.

Solo llega a `features.separation_fall_risk_current` un ciclo que cumpla:

- `resultado_ciclo='ABIERTA'`;
- separación fuente `estado='Activo'`;
- `proforma_first_seen_at >= observed_at - interval '3 months'`;
- `proforma_first_seen_at <= observed_at`.

`proforma_first_seen_at` usa `MIN(raw_cygnus.proforma_unidad.fecha_creacion)` por `codigo_proforma`. Se elige el mínimo para impedir que un duplicado reciente o una unidad añadida después rejuvenezcan artificialmente una proforma histórica.

La frontera exacta de tres meses está incluida. Se usan meses calendario, no 90 días fijos.

## 4. Validar el feature contract

```powershell
python -m cygnus_decision_engine --env-file .env validate-separation-risk
```

El gate bloquea decisiones si detecta:

- duplicados en candidatos actuales;
- candidatos `BLOCKED`;
- `observed_at` faltante;
- cualquier candidato actual fuera de la ventana de tres meses;
- una proforma con fecha posterior a `observed_at`;
- desacuerdo entre conteo elegible, actual y distinto.

No falla por proformas antiguas: son exclusiones deliberadas y quedan contabilizadas. Una fecha de proforma faltante también queda excluida y reportada como deuda de completitud.

### Semántica de features provisional

La identidad, lifecycle y elegibilidad temporal sí son gobernados. Dos señales siguen explícitamente como `WARN`:

- `interaction_count_14d`: proxy binario 0/1 construido con la última interacción conocida por cliente+proyecto;
- `has_pending_admin_block`: `NULL` hasta certificar la regla administrativa.

## 5. Prueba sin escritura

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --dry-run --top 20
```

El output incluye, además del score:

- proyecto, unidad, proforma y asesor;
- `proforma_first_seen_at`;
- `proforma_age_days`;
- regla de elegibilidad;
- edad de separación y recencia de interacción.

## 6. Persistir la primera corrida

Solo después de revisar el dry-run:

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --top 20
```

La escritura es idempotente para:

`decision_key + entity_type + entity_id + observed_at + policy_version`.

## 7. Consumir la cola comercial

```sql
select *
from decision_intelligence.v_separation_fall_risk_worklist
order by action_priority, score desc nulls last, separation_id;
```

La worklist conserva la evidencia de elegibilidad de proforma dentro de `feature_snapshot`.

## 8. Tests de calidad recomendados

### Gate duro por corrida

Deben permanecer en cero:

- `duplicate_candidates`;
- `quality_blocked`;
- `missing_observed_at`;
- `current_outside_proforma_recency_window`;
- `excluded_proforma_after_observed_at`.

Y debe cumplirse:

`candidates = eligible_candidates = distinct_candidates`.

### Monitoreo de calidad, sin bloquear inicialmente

Observar tendencia de:

- `excluded_proforma_older_than_3_months`;
- `excluded_missing_proforma_date`;
- porcentaje `eligible_candidates / universe_candidates`;
- cantidad sin interacción reciente;
- cantidad pendiente de certificar señal administrativa.

Un salto brusco en estos indicadores debe investigarse aunque el gate duro pase.

### Tests de regresión recomendados

1. **Frontera temporal:** exactamente `observed_at - 3 months` debe entrar; un instante anterior debe salir.
2. **No rejuvenecimiento:** una proforma antigua con una segunda fila reciente en `proforma_unidad` debe seguir siendo antigua por `MIN(fecha_creacion)`.
3. **No leakage:** `proforma_first_seen_at > observed_at` debe bloquear el gate.
4. **Idempotencia:** dos corridas del mismo snapshot no duplican recomendaciones.
5. **Estabilidad de volumen:** alertar si el universo elegible cambia de forma material sin un cambio equivalente en RAW.
6. **Backtest de utilidad:** comparar top-N del baseline contra caídas/ventas observadas posteriormente y contra una política ingenua de “más antiguas primero”.

## Definition of Done

La primera decisión se considera operativa cuando:

- el feature contract nace del lifecycle certificado;
- la ventana de tres meses está aplicada y auditable;
- el gate devuelve 0 fallos duros;
- el dry-run produce una priorización comercialmente razonable;
- dos ejecuciones del mismo snapshot no duplican recomendaciones;
- la cola puede consultarse desde SQL/Power BI;
- al menos una recomendación puede enlazarse a feedback humano y outcome.

## Próxima mejora

Antes de entrenar ML, sustituir los proxies actuales por:

1. conteo exacto de interacciones point-in-time 7/14/30 días;
2. regla certificada de bloqueo administrativo.

El baseline seguirá siendo el benchmark que el primer modelo supervisado deberá superar out-of-time.
