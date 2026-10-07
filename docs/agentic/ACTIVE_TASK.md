# Active Task

Task ID: ABSORCION-NP-A-001
Title: Torre Nápoles solo subdivisión NP-A en absorción reconstruida
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: fix/absorcion-np-a
Base branch: main

## Objective

Excluir subdivisiones no habilitadas de NP de stock y ventas reconstruidos.

## Next action

Aplicar commit y schema_sync --only absorcion_ventas_mensual en Medallio local;
validar SQL y actualizar Power BI. Ver docs/ABSORCION_VENTAS_MENSUAL.md.

## Previous task

CLIENTES-DQ-INCREMENTAL-001 conserva su verificación Windows pendiente en PR 40.
