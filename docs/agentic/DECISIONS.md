# Decisions

## MAP-ADR-001 — Git repository is the shared agent memory

Date: 2026-09-30  
Status: ACCEPTED

### Decision

Durable cross-agent context lives in versioned repository files and Git history, not in any model's private conversation history.

### Rationale

ChatGPT, Claude, humans, and future tools do not share identical memory. Git is inspectable, portable, diffable, and model-independent.

### Consequence

A handoff is complete only when enough state exists in the repository for another competent agent to continue.

---

## MAP-ADR-002 — Human-readable Markdown plus machine-readable JSON

Date: 2026-09-30  
Status: ACCEPTED

### Decision

MAP uses Markdown for reasoning/context and `.agent/state.json` for structured state.

### Rationale

Humans and models benefit from prose; scripts and future automation need deterministic fields.

---

## MAP-ADR-003 — Repository evidence outranks agent memory

Date: 2026-09-30  
Status: ACCEPTED

### Decision

Observed code/runtime/tests/schema/Git evidence outranks MAP prose and prior conversations.

### Rationale

Agent summaries can become stale. Executable evidence should correct documentation, not the reverse.

---

## MAP-ADR-004 — One active writer per task

Date: 2026-09-30  
Status: ACCEPTED

### Decision

A task has one active writer/owner at a time. Another agent may review from a checkpoint, or parallel work must use separate task IDs/branches.

### Rationale

This reduces conflicting edits and ambiguous ownership during ChatGPT ↔ Claude handoffs.

---

## MAP-ADR-005 — Handoffs contain no secrets or raw PII

Date: 2026-09-30  
Status: ACCEPTED

### Decision

MAP documents may name environment variables and data contracts but must never store secret values, tokens, credentials, or raw customer PII.

### Rationale

Agentic state is versioned and may be broadly visible to repository collaborators.

---

## MAP-ADR-006 — Protocol is vendor-neutral

Date: 2026-09-30  
Status: ACCEPTED

### Decision

The core protocol is named MEDALLIO AGENT PROTOCOL rather than after ChatGPT or Claude.

### Rationale

The coordination layer should survive model/provider changes. Provider-specific files are entrypoints into the same shared state.

---

## MAP-ADR-007 — Night Shift OS sits above MAP

Date: 2026-10-01  
Status: ACCEPTED

### Decision

MAP remains the cross-agent state/handoff protocol. Night Shift OS adds portfolio queueing, unattended-work policies, budgets, and morning reporting without replacing MAP.

### Rationale

State continuity and work selection are different responsibilities. Separating them keeps the core protocol portable.

---

## MAP-ADR-008 — Unattended pilot cannot perform irreversible production actions

Date: 2026-10-01  
Status: ACCEPTED

### Decision

During the 2026-10-01 through 2026-10-07 pilot, agents may create branches, code, tests, documentation, artifacts, and draft PRs, but may not merge main, production-deploy, publish stores, or execute destructive production writes.

### Rationale

The first week should maximize verifiable production while keeping irreversible decisions human-controlled.

---

## MAP-ADR-009 — One task in flight overnight by default

Date: 2026-10-01  
Status: ACCEPTED

### Decision

Night Shift OS targets one concurrent task and at most two task starts per night, with one automatic rework cycle.

### Rationale

This limits quota burn, duplicate work, CI congestion, and context fragmentation while the workflow is being validated.

---

## MAP-ADR-010 — ChatGPT builds; Claude challenges

Date: 2026-10-01  
Status: ACCEPTED

### Decision

The pilot targets approximately 90% primary work through ChatGPT/Work/Codex and 10% through Claude as a selective reviewer/challenger.

### Rationale

The second model adds more value by testing assumptions and finding failure modes than by duplicating the same implementation.

---

## MAP-ADR-011 — Stock reconstruido por altas de proyecto y ventas

Date: 2026-10-02
Status: ACCEPTED

El usuario aprobó un cuadro adicional desde enero 2024: todas las unidades de
departamentos ingresan el primer día del mes indicado en su CSV de 17 proyectos.
Las separaciones y caídas no generan movimientos en este cuadro. Se conserva la
regla canónica de fecha y el veto de respaldo de Venta para separaciones desde 2026.
No se reemplazan ledger ni snapshots observados. Se reutilizan ventas reconciliadas;
casos ambiguos siguen visibles y excluidos, sin redefinir anulación de ventas.
La capa usa vistas sobre CORE/analytics y se instala mediante schema_sync, sin nuevas
consultas a Redshift. Los saldos deben etiquetarse como reconstruidos, no observados.


## MAP-ADR-012 — Ventas vigentes retrospectivas y evidencia temporal

Date: 2026-10-02
Status: ACCEPTED — supersedes sales eligibility and project-start clauses of ADR-011

El usuario aprobó adelantar el inicio al primer mes de venta documental cuando sea
anterior al adjunto, manteniendo ambas fechas y comentarios. Aprobó aceptar fechas
documentales anteriores a separación y excluir retrospectivamente proformas anuladas.
El reporte no exige transición del ledger; utiliza ciclos existentes, extras y procesos
de la réplica local. CI tiene prioridad; Venta Activo solo respalda separaciones
originales Y analíticas anteriores a 2026. Un pago mal formado no habilita fallback.
Anulaciones se enlazan por proforma/unidad hasta hoy, sin umbral de separación legacy.
Más de una venta vigente por unidad queda pendiente. No se modifica Phase B ni sus
controles. Los casos se entregan mediante una vista de observaciones sin PII.
La tabla futura de seguimiento temporal de venta/anulación/reventa queda pendiente;
este cuadro no sirve para reconstruir lo que se sabía en un corte pasado.


## MAP-ADR-013 — Forecasting comercial con evidencia prospectiva

Date: 2026-10-03
Status: ACCEPTED

El usuario autorizó implementar el piloto completo en bd_replica_crm. Se añade
un producto independiente usando el contrato confirmado de absorción, sin tocar
CI/ventas canónicas ni generar carga Redshift. Histórico revisado se identifica
como diagnóstico; snapshots y predicciones nuevas se preservan append-only y
los primeros resultados maduros se congelan. Comparar promedio, ETS, GMM y bosque;
seleccionar en validación separada de prueba final, sin promoción automática.
Horizontes acumulados sobre stock existente, sin elasticidad causal ni caja.
La ampliación de señales CRM con fechas históricas verificables permanece
pendiente de contratos; no se inventan variables en SQL.
