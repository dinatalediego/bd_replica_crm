# Active Task

Task ID: FORECAST-EVIDENCE-001
Title: Forecasting comercial con entrenamiento y evidencia
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/forecasting-evidence-pilot
Base branch: main

## Objective

Implementar dataset/diagnóstico, entrenamiento, evaluación temporal, predicciones
versionadas y seguimiento comercial usando Medallio local.

## Scope and decisions

ADR-013. Histórico retrospectivo es diagnóstico; snapshots/predicciones/outcomes
append-only. Cuatro modelos, candidatos elegidos en validación, prueba final
reservada, bandas empíricas sin garantía de cobertura. Ventas acumuladas del
stock existente; sin carga Redshift, cambios de CI/canónico o promoción automática.
No hay acceso al PostgreSQL real del usuario.

## Evidence

238 pruebas locales aprobadas, 24 omitidas por falta de PostgreSQL desechable.
Demo ejecutada: entrenamiento, artefactos y predicciones SYNTHETIC_ONLY.
CI 37150045806: 156 pruebas de plataforma + 106 de motor aprobadas.
Revisión final agrega embargo, serialización ETS y prueba del adaptador.
Notebook ejecutado de extremo a extremo. CI final pendiente.

## Next action

Ejecutar scripts/64_forecasting_medallio.bat en PC con .env PostgreSQL y fuente
actualizada. Inspeccionar report.html, registrar metas/acciones y conectar vistas
Power BI según docs/COMMERCIAL_FORECASTING.md.

## Previous task

ABS-2024-VENTAS queda con validación real local pendiente; se conservan reglas
ADR-012 y contrato de absorción. No se altera cola nocturna.
