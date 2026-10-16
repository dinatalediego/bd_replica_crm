# Decision Room funnel contracts

Este componente expone tres productos agregados para la Sala de decisiones sin publicar PII:

1. `analytics.v_decision_room_funnel_monthly`: actividad por mes de evento (`EVENT_MONTH_NOT_COHORT`). Sirve para describir qué pasó en cada mes, pero no autoriza tasas de conversión entre columnas.
2. `analytics.v_decision_room_identity_audit_monthly`: auditoría de identidad y de semántica de `raw_cygnus.clientes_proyectos`. Distingue una fuente que se comporta como entrada persona-proyecto (`PERSON_PROJECT_ENTRY_LIKE`) de una tabla con múltiples eventos por persona-proyecto (`MULTI_EVENT_LEAD_LIKE`) y expone mapeados, ambiguos y sin match.
3. `analytics.v_decision_room_funnel_cohort_monthly`: cohortes por mes de captación. Cada `persona_key × codigo_proyecto` se ancla en `fecha_primer_lead`; solo cuenta proforma, separación y minuta ocurridas en o después de la captación. Publica tasas realizadas a la fecha de corte y tasas comparables de maduración a 30, 60 y 90 días.

## Interpretación

- `lead_to_*_realized_rate` es una tasa observada a la fecha actual y está censurada para cohortes recientes.
- `lead_to_*_30d_rate`, `60d` y `90d` usan únicamente leads con exposición completa a esa ventana.
- `temporal_anomaly_rows > 0` marca evidencia donde una etapa aparece antes del lead o rompe el orden proforma → separación → minuta. No se corrige silenciosamente.
- `multi_project_documents` no es un error por sí mismo: una misma persona puede interesarse en varios proyectos.

## Validación local recomendada

```sql
SELECT *
FROM analytics.v_decision_room_identity_audit_monthly
WHERE codigo_proyecto IN ('MT','NP')
ORDER BY codigo_proyecto, periodo_mes;

SELECT *
FROM analytics.v_decision_room_funnel_cohort_monthly
WHERE codigo_proyecto IN ('MT','NP')
ORDER BY codigo_proyecto, cohort_month;
```

Antes de incorporar estas cohortes al JSON de la Sala se debe comprobar en PostgreSQL local que la identidad, la cronología y los denominadores maduros son consistentes con los datos reales.
