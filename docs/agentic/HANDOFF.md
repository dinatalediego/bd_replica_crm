# Latest Handoff

Protocol: MEDALLIO AGENT PROTOCOL 1.0
Generated at: 2026-10-07T04:42:02Z
Task: ABSORCION-NP-A-001 — Torre Nápoles solo NP-A en absorción reconstruida
From: chatgpt
To: human
Status: REVIEW_READY
Branch: fix/absorcion-np-a
Commit at checkpoint: 3287d20560124b3fb2c5a7e55223c79a4a22804a

## Exact next action

Aplicar commit NP-A, schema_sync del componente y validar SQL/Power BI local

## Working-tree state

Dirty: yes

### Changed files

- M .agent/state.json
- M docs/ABSORCION_VENTAS_MENSUAL.md
- M docs/agentic/ACTIVE_TASK.md
- M docs/agentic/DECISIONS.md
- M docs/agentic/HANDOFF.md
- M scripts/schema_sync.py
- M sql/96_absorcion_ventas/01_contract.sql
- M sql/96_absorcion_ventas/02_validation.sql
- M tests/integration/test_absorcion_ventas_postgres.py

### Diff stat

```text
.agent/state.json                                  | 25 +++----
 docs/ABSORCION_VENTAS_MENSUAL.md                   | 35 +++++++++
 docs/agentic/ACTIVE_TASK.md                        | 24 ++-----
 docs/agentic/DECISIONS.md                          | 11 +++
 docs/agentic/HANDOFF.md                            | 82 ++++++++++++++++------
 scripts/schema_sync.py                             |  1 +
 sql/96_absorcion_ventas/01_contract.sql            | 13 +++-
 sql/96_absorcion_ventas/02_validation.sql          | 15 ++++
 .../integration/test_absorcion_ventas_postgres.py  | 33 +++++++--
 9 files changed, 178 insertions(+), 61 deletions(-)
```

### Staged diff stat

```text
(none)
```

## Validation / tests recorded for this checkpoint

- 27 escenarios de absorción ejecutados y aprobados en PGlite PostgreSQL WASM

## Notes

- pytest PostgreSQL nativo bloqueado por restricciones de usuario del entorno; mismos 27 escenarios ejecutados mediante adaptador PGlite temporal
- Sin acceso a Medallio real. RAW/CORE/ledger y predicciones emitidas conservados.

## Recent commits

- 3287d20 Pause automatic CI; keep manual workflow dispatch
- c00d525 Incorporar cortes comerciales y escenarios de impacto ML en Medallio (#42)
- 0c1b83b Clientes calidad incremental: recuperar 02b sin reconstruir todos los clientes cada hora (#40)
- 5808037 Forecasting comercial: entrenamiento reproducible y evidencia prospectiva (#39)
- c4fb51f Corregir nombres vacíos de raw_mercado.unidades para Power BI (#37)

## Handoff rule

The receiving agent must inspect the real repository state and diff before trusting this summary. Code/runtime evidence and tests outrank this file.
