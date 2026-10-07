# Latest Handoff

Protocol: MEDALLIO AGENT PROTOCOL 1.0
Generated at: 2026-10-07T20:18:51Z
Task: EVOLUCION-COMERCIAL-001 — Panel por edad comercial, composición y precios normalizados
From: chatgpt
To: human
Status: REVIEW_READY
Branch: feat/evolucion-comercial
Commit at checkpoint: a5cfe11c524fa30be8084858b048cbf7b2fbf1a2

## Exact next action

Aplicar rama y ejecutar docs/EVOLUCION_COMERCIAL.md en Medallio local

## Working-tree state

Dirty: yes

### Changed files

- M docs/agentic/ACTIVE_TASK.md
- M docs/agentic/DECISIONS.md
- M scripts/schema_sync.py
- ?? docs/EVOLUCION_COMERCIAL.md
- ?? scripts/refresh_evolucion_comercial.py
- ?? sql/99_evolucion_comercial/
- ?? tests/integration/evolucion_comercial_assertions.sql
- ?? tests/integration/evolucion_comercial_fixture.sql
- ?? tests/integration/test_evolucion_comercial_postgres.py

### Diff stat

```text
docs/agentic/ACTIVE_TASK.md | 21 ++++++++++++++-------
 docs/agentic/DECISIONS.md   | 15 +++++++++++++++
 scripts/schema_sync.py      | 13 +++++++++++++
 3 files changed, 42 insertions(+), 7 deletions(-)
```

### Staged diff stat

```text
(none)
```

## Validation / tests recorded for this checkpoint

- 16 aserciones SQL aprobadas en PostgreSQL WASM PGlite; instalación repetida aprobada; compilación Python aprobada

## Notes

- Sin acceso a Medallio real; pytest nativo skipped sin DSN; captura de precios comienza al ejecutar refresh local

## Recent commits

- a5cfe11 Excluir NP-B de absorción y stock reconstruidos de Torre Nápoles
- 3287d20 Pause automatic CI; keep manual workflow dispatch
- c00d525 Incorporar cortes comerciales y escenarios de impacto ML en Medallio (#42)
- 0c1b83b Clientes calidad incremental: recuperar 02b sin reconstruir todos los clientes cada hora (#40)
- 5808037 Forecasting comercial: entrenamiento reproducible y evidencia prospectiva (#39)

## Handoff rule

The receiving agent must inspect the real repository state and diff before trusting this summary. Code/runtime evidence and tests outrank this file.
