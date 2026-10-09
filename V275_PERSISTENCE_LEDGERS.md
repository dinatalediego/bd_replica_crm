# Medallio v2.7.5 — Safe Evidence/Outcome Persistence

Tu runtime v2.7.4.1 ya confirmó:

```text
DB bridge: OK
states=17
actions=10
Google JSON coercion: OK
L2 Diagnóstico & Comparabilidad: PASS
```

Lo único faltante son las tablas persistentes de Evidence & Outcome.

## Importante

NO uses el migration SQL antiguo de v2.7 sin este parche.

Ese contrato también creaba:

```text
analytics.v_project_growth_state
```

y podría reemplazar la vista gobernada construida en v2.7.2.

v2.7.5 instala solamente los ledgers persistentes y preserva:

```text
analytics.v_project_growth_state
```

como fuente gobernada de negocio.

## Instala

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\69_install_evidence_outcome_persistence.ps1
```

Debe dejar en OK:

```text
model_control.evidence_gate
analytics.project_growth_state_snapshot
decision_intelligence.decision_ledger
decision_intelligence.action_log
decision_intelligence.outcome_ledger
experiments.baseline_challenger
analytics.v_project_growth_state  (preserved)
```

## Después

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

Esperado:

```text
altitude=L2 Diagnóstico & Comparabilidad
next=PREDICTIVE BLOCK
db_sync.status=OK
```

y luego:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

A partir de esa corrida Medallio empezará a acumular históricamente:
- gates,
- snapshots por proyecto,
- decisiones,
- acciones,
- outcomes,
- experimentos.

Eso habilita la memoria necesaria para L5/L6/L7 sin alterar el contrato L2.
