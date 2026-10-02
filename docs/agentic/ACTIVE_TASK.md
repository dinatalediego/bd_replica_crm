# Active Task

Task ID: ABS-2024-VENTAS
Title: Stock pendiente de venta y absorción mensual por proyecto
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/absorcion-mensual-ventas-2024
Base branch: main

## Objective

Reconstruir stock desde enero de 2024 con altas por proyecto del adjunto del usuario
y ventas canónicas existentes. Separaciones y caídas no mueven este stock.

## Decisions and scope

Mantener prioridad de pago CI y prohibición de fallback de Venta para separaciones
desde 2026. No se modificaron Phase B, controles de pago CI ni ledger operativo.
Se reutiliza CORE unidades y reconciliación. Vistas vivas instaladas con schema_sync;
sin nuevo job ni carga Redshift. Detalle, mensual e incidencias disponibles.

## Evidence

36 tests passed: 14 casos PostgreSQL sintético + 22 contratos de regresión.
Corrección validada: adaptador propio de reconciliación con columnas explícitas,
conservando vistas legacy y soportando columnas nuevas en Phase B.
SQL probado con instalación idempotente; Python compilado; git diff --check limpio.
Documento de operación: docs/ABSORCION_VENTAS_MENSUAL.md.

## Next action

Revisar la rama, ejecutar instalación/refresh local y validar totales reales e
incidencias con sql/96_absorcion_ventas/02_validation.sql. No hay acceso desde esta
sesión a Medallio local. No se afirma validación con datos reales ni despliegue local.

## Other work

NIGHT-002 era el checkpoint previo de main; esta rama no modifica su cola ni sus
políticas. La tarea interactiva ABS-2024-VENTAS es independiente.
