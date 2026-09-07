# Power BI — Medallio Control Tower

Contenido:

- `M/`: parámetros y consultas Power Query M.
- `DAX/`: medidas por página.
- `model/`: relaciones, grano y diccionario KPI-negocio.
- `pages/`: especificación visual de las 4 páginas.
- `theme/`: tema JSON importable.
- `POWER_BI_BUILD_STEP_BY_STEP.md`: construcción paso a paso del PBIX.

## Qué está operativo en Sprint 1

- Página 01 Data Platform: **sí**.
- Página 02 Data Quality: **sí**, después del primer control profundo.
- Página 03 Models & MLOps: estructura preparada; se poblará al registrar modelos/scoring.
- Página 04 Decisions & Learning: estructura preparada; se poblará al registrar recomendaciones, acciones y outcomes.

El loop Lead Scoring v0.2 agrega dos consultas listas para pegar en Power Query:

- `M/qLeadActionOutcome.m`: trazabilidad individual score → acción → outcome.
- `M/qLeadActionOutcomePerformance.m`: cohortes observacionales por banda y acción.

El diseño evita falsos KPIs: una página futura puede estar vacía hasta que el proceso de negocio realmente genere esos eventos.
