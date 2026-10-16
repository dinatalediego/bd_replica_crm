# Medallio Decision OS v1

## Objetivo

Medallio deja de tratar el output de un modelo como el producto final. El objeto central es una decision empresarial trazable:

`Prediction / Evidence -> Decision -> Action -> Outcome -> Learning`

`Economic Value` vive en paralelo como un ledger versionado que permite comparar lo esperado, aprobado y realizado sin perder historia.

## Objetos de primera clase

| Objeto lógico | PostgreSQL local | Supabase |
|---|---|---|
| Decision | `decision_intelligence.decision_ledger` | `decision_intelligence.decisions` |
| Action | `decision_intelligence.action_log` | `decision_intelligence.actions` |
| Outcome | `decision_intelligence.outcome_ledger` | `decision_intelligence.outcomes` |
| Economic Value | `decision_intelligence.economic_value_ledger` | `decision_intelligence.economic_values` |
| Expert / Committee Review | `decision_intelligence.decision_reviews` | `decision_intelligence.decision_reviews` |
| Model Link | `decision_intelligence.decision_model_links` | `decision_intelligence.decision_model_links` |
| Decision Queue | `decision_intelligence.v_decision_queue` | `decision_intelligence.v_decision_queue` |

La diferencia física entre local y Supabase es intencional en v1. El repositorio ya contenía contratos distintos; esta entrega añade una capa compatible y no destructiva, sin renombrar ni borrar objetos existentes.

## Economic Value

Cada valoración guarda:

- `value_stage`: `EXPECTED`, `APPROVED`, `REALIZED`, `COUNTERFACTUAL`.
- `value_type`: revenue, margin, cost saving, avoided risk, opportunity u otro.
- baseline y comparación.
- costo directo y costo de oportunidad.
- valor incremental neto.
- probabilidad y confianza.
- horizonte, método, versión de fórmula, supuestos y metadata.

La vista de reconciliación usa solo la valoración vigente por `decision_id + value_name`. Una valoración `APPROVED` tiene precedencia sobre una `EXPECTED`; las versiones históricas permanecen en el ledger para auditoría.

## Governance / readiness

La vista `v_decision_operating_system` combina:

- decisión;
- acciones y outcomes;
- economic value esperado y realizado;
- revisión Data Science;
- revisión Business / Comité Gerencial;
- vínculo a modelos / predicciones.

La cola asigna un estado de preparación:

- `ECONOMIC_VALUE_MISSING`
- `DATA_SCIENCE_REVIEW_MISSING`
- `BUSINESS_REVIEW_MISSING`
- `REVIEW_PENDING`
- `READY_FOR_DECISION`
- `BLOCKED`

La prioridad económica usa primero el valor esperado ajustado por confianza.

## Seguridad Supabase

Las nuevas tablas online tienen RLS activado y no se añadieron políticas ni grants para `anon` o `authenticated`. En v1 son objetos backend/service-only. Las vistas nuevas son `security_invoker`, no `security_definer`.

## Instalar en PostgreSQL local

Desde `C:\Cygnus\projects\bd_replica_crm`:

```powershell
git fetch origin
git switch feat/medallio-decision-os-v1
python scripts/schema_sync_decision_os.py --status
python scripts/schema_sync_decision_os.py
python scripts/schema_sync_decision_os.py --status
```

El instalador reutiliza el registry/checksum del `schema_sync.py` existente, pero está aislado para no alterar el ciclo horario general durante la validación inicial.

## Tests Python

```powershell
pytest -q tests/test_economic_ledger.py
```

El test valida que el Economic Value generado desde `EconomicPolicy/economic_value()` conserve la matemática del motor existente y que los costos no se resten dos veces.

## Smoke queries

```sql
SELECT *
FROM decision_intelligence.v_decision_queue
LIMIT 50;
```

```sql
SELECT
    decision_id,
    expected_value,
    expected_confidence_adjusted_value,
    realized_value,
    value_gap,
    realization_ratio
FROM decision_intelligence.v_economic_value_reconciliation
ORDER BY latest_expected_valuation_at DESC NULLS LAST;
```

## Flujo operativo objetivo

1. Un modelo, regla, analista o RAG produce evidencia/predicción.
2. Se crea o enriquece una `Decision`.
3. El motor económico registra `Economic Value EXPECTED`.
4. Data Science revisa calidad, leakage, backtest, drift, calibración y límites de uso.
5. Comité/Business revisa sentido comercial, factibilidad y riesgo.
6. `v_decision_queue` prioriza lo listo para decidir por valor económico ajustado por confianza.
7. Una decisión aprobada genera una o más `Action`.
8. Se registran `Outcome` y `Economic Value REALIZED`.
9. Se calcula `value_gap` y `realization_ratio`.
10. El resultado alimenta `Learning`, experimentación y futuras versiones del modelo.

## Qué NO hace esta v1

- No reemplaza los ledgers ni modelos existentes.
- No publica estas tablas directamente al cliente Android/web.
- No concede acceso a `anon`/`authenticated`.
- No incorpora todavía la nueva capa al scheduler horario general.
- No obliga a que toda decisión provenga de ML: una decisión humana puede existir y luego enlazar evidencia/modelos.

## Siguiente corte funcional

La siguiente versión debe poblar la cola con casos reales de pricing, forecast y lead scoring, y exponer un API controlado para las pantallas `Today`, `Decision Room` y `Model Observatory`.
