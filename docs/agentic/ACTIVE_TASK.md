# Active Task

Task ID: CLIENTES-DQ-INCREMENTAL-001
Title: Refresh incremental de clientes_calidad y recuperación de 02b
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/clientes-calidad-incremental
Base branch: main

## Objective

Procesar solo altas/cambios desde RAW PostgreSQL y volver a activar 02b en la PC,
conservando reglas DQ y reparaciones locales de portal/config/orquestador.

## Evidence

135 pruebas locales de plataforma y 106 de motor aprobadas. Pruebas SQL
sintéticas en PGlite: DQ, cambios/bajas/no-op, hash sin metadatos, rollback,
paridad full, reglas y migración. CI PostgreSQL y validación PC pendientes.
No se accedió al PostgreSQL real ni al Scheduler Windows.

## Next action

Seguir docs/CLIENTES_CALIDAD_INCREMENTAL.md: aplicar commit, instalar componente,
ejecutar DQ dos veces, habilitar 02b con helper, validar DW_REFRESH_OK y reactivar
el trigger. Verificar LastTaskResult=0 en siguiente ejecución Windows.

## Previous task

FORECAST-EVIDENCE-001 quedó publicado en PR #39. Mantiene validación real local
pendiente y decisiones ADR-013. No se modifica cola nocturna ni ventas canónicas.
