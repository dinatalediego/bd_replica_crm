# Auditoría de identidad MT / NP — 2026-10-16

## Evidencia local aportada

Para `raw_cygnus.clientes_proyectos`, entre 2025-01 y 2026-10:

- Matera (`MT`): 6,629 filas, 6,629 ids distintos y 6,629 documentos distintos en el agregado mensual revisado.
- Torre Nápoles (`NP`): 14,582 filas, 14,582 ids distintos y 14,582 documentos distintos en el agregado mensual revisado.
- En las 33 combinaciones proyecto-mes observadas: `filas = leads_por_id = personas_por_documento` y `repetidos_aprox = 0`.
- La consulta por `codigo_proyecto + documento` con `HAVING count(*) > 1` no devolvió registros para MT/NP.

## Interpretación

En estos dos proyectos y en el período auditado, `clientes_proyectos` se comporta como una fuente de **entrada persona-proyecto** más que como un log de múltiples eventos de lead. Por eso el funnel de actividad muestra `leads = clientes_unicos` cuando la resolución de identidad es completa.

Esto no demuestra que la propiedad se cumpla para todos los proyectos ni para siempre. El contrato `analytics.v_decision_room_identity_audit_monthly` la vigila de forma agregada y clasifica la fuente como `PERSON_PROJECT_ENTRY_LIKE` o `MULTI_EVENT_LEAD_LIKE`.

Una misma persona sí puede aparecer en proyectos distintos; `multi_project_documents` se reporta como linaje comercial, no como error.

## Implicación para cohortes

El funnel de cohortes usa `analytics.marketing_audiencias_proyectos`, cuya llave es `persona_key × codigo_proyecto`, y ancla la cohorte en `fecha_primer_lead`. Solo se consideran conversiones las proformas, separaciones o minutas cuya fecha es igual o posterior a esa captación. Las anomalías temporales se reportan y no se corrigen silenciosamente.
