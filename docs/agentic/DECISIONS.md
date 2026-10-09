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


## MAP-ADR-014 — DQ incremental local por identidad/hash

Date: 2026-10-04
Status: ACCEPTED

El usuario pidió rediseñar clientes_calidad y recuperar 02b. Se preservan reglas
y campos DQ; se compara id/hash en snapshot RAW local excluyendo solo metadatos
ETL verificados. Se reemplazan únicamente identidades nuevas/modificadas y se
propagan bajas presentes en RAW. Detección O(n) local, sin nuevas consultas
Redshift. Bootstrap/cambio de definición recalcula una vez; runs agregados
registran evidencia sin PII. Gate SQL y Python anterior a commit, locks y timeout.
Se conserva Step 02b existente en Git y se añade helper para habilitar únicamente
el bloque comentado conocido del PC, respaldando y preservando otras reparaciones.
Activación real Windows y duración sobre Medallio requieren verificación local.


## MAP-ADR-015 — Universo habilitado Torre Nápoles

Date: 2026-10-07
Status: ACCEPTED — supersedes NP population clause of ADR-011

Usuario confirma que NP-B no fue liberada. Absorción reconstruida admite solo
NP-A para NP (incluidas sus ventas históricas), sin alterar otros proyectos.
Filtro compartido anterior a ciclos, primera venta documental y saldos mensuales.
RAW/CORE/ledger y snapshots emitidos se preservan. Sin nueva carga Redshift.

## MAP-ADR-016 — Panel comercial por edad y precios observados

Date: 2026-10-07
Status: ACCEPTED

Nueva capa local independiente: panel unidad-mes y proyecto-mes desde inicio efectivo
hasta agotamiento/presente, heredando NP-A y ventas vigentes retrospectivas. Stock
inicial de mes 1 incluye alta inicial. Exposición en días y atributos actuales
permiten comparar composición con limitaciones explícitas. Precios de lista se
observan desde instalación, primera captura diaria preservada; variables predictoras
usan observación anterior al mes. Índice geométrico nominal base 100 de cesta fija
por proyecto/moneda, NULL si cobertura incompleta. No se inventa historia ni se
estima elasticidad causal. Estacionalidad y estacionariedad requieren análisis
posterior sobre el panel. Sin nuevas consultas Redshift ni programación automática.

## MAP-ADR-017 — Datasets econométricos históricos y captura programada

Date: 2026-10-07
Status: ACCEPTED

Usuario autoriza tablas para las siete recomendaciones, cálculo histórico y captura
programada. Nueva capa local integra eventos versionados, snapshots diarios, ofertas,
etapas, demanda, contexto importable, predictores y objetivos por corte/horizonte.
Reconstruido se revisa sin presentarlo como evidencia histórica conocida. Observado
es inmutable; resultados revisados dejan versiones. Primer resultado maduro sin
alertas/fresco se usa en evaluación prospectiva. Fuentes externas sin contrato no
se inventan: importadores documentados y estados de cobertura. Se reutilizan
registros forecasting existentes; no se entrenan/promocionan nuevos modelos.
El paso 07b del maestro horario procesa una vez al día tras CORE/ventas. Instalador
local con alternativa de tarea Windows explícita; no ejecución remota del PC.
Sin consultas Redshift añadidas ni reactivación de Actions. NP-A se conserva.


<!-- PR #41 decisions formerly numbered 015/016; renumbered 018/019 to retain main decisions without collisions. -->
## MAP-ADR-018 — Selección conservadora y evidencia comparable

Date: 2026-10-04
Status: ACCEPTED — strengthens evaluation and monitoring in ADR-013

El usuario pidió fortalecer la arquitectura con sus artifacts reales. La selección
usa únicamente trayectorias completas de validación, controles por proyecto y
políticas con fallback comparadas sobre la misma población. Se exige soporte
temporal no solapado, cobertura e incremento mínimo de rendimiento; esos umbrales
son configurables y no prueban significancia. Con evidencia insuficiente se conserva
mean3 y los candidatos ML siguen shadow. La prueba histórica ya inspeccionada
sirve como diagnóstico de desarrollo, no como confirmación virgen de esta versión.

Cada run registra cobertura por proyecto y stock, revisiones del snapshot, rangos
de entrenamiento, calibración, bytes de código y hashes. La medición congela el
primer snapshot completo por proyecto y verifica compatibilidad con el stock emitido.
Se distinguen emisión antes del inicio de la ventana y emisión durante ella, usando
America/Lima; outcomes legacy no se recertifican retroactivamente. No se modifican
ventas canónicas, no se consulta Redshift, no se promueve ni fusiona automáticamente.
Los datos comerciales adjuntos se auditan de forma privada; no se publican en GitHub.


## MAP-ADR-019 — Revisión por unidad y presentación de evidencia emitida

Date: 2026-10-04
Status: ACCEPTED — adds a read-only diagnostic and Power BI layer to ADR-018

El panel comercial suministrado tiene filas mensuales con revisión para NP, SL
y TZ, pero la función mensual cruza cada mes con el mismo estado ACTUAL de las
unidades. Cada proyecto marca una unidad en todos sus meses: son tres unidades
actuales por investigar, sin asumir el motivo documental de ninguna. Se entregan
consultas de lectura a las vistas unitarias y de ciclos existentes. No se cambia
requiere_revision ni se reduce retrospectivamente el stock para ocultar el caso;
la resolución exige fuente/documentación local y una nueva versión de pronóstico.

El tablero usa vistas ya instaladas con grano explícito: cobertura solo del último
run, pronóstico seleccionado por horizonte, fila de revisión por unidad y resultado
emitido por run/proyecto/horizonte. MAE, sesgo y WAPE se calculan con el mismo filtro
de elegibilidad y quedan vacíos hasta que exista resultado maduro compatible; un
horizonte acumulado único evita sumar varias ventanas superpuestas. Los modelos
candidatos se muestran como entrenamiento/propuesta aunque no sean seleccionados.
No hay acceso a PostgreSQL real ni modificación automática de la fuente de Medallio.


## MAP-ADR-020 — Productos analíticos portables y evidencia

Date: 2026-10-09
Status: ACCEPTED

El usuario autorizó desarrollar y desplegar los 12 puntos de la propuesta Atlas.
Se añade publishing sin reorganizar ni cambiar contratos de réplica/analytics.
Packs JSON versionados, registro privado inmutable y feedback de decisiones.
La publicación incluida usa solo fixture sintética verificable. El agregado real
sigue PRIVATE; no hay acceso directo Android a PostgreSQL. Tipos de evidencia no
son una escala universal de calidad. Baseline de media móvil con evaluación
temporal; sin elasticidad causal, promoción automática, nuevas consultas Redshift
ni reactivación de Actions. Instalar publishing es opt-in en schema_sync.
