# Active Task

Task ID: EVOLUCION-COMERCIAL-001
Title: Panel por edad comercial, composición y precios normalizados
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/evolucion-comercial
Base branch: main

## Objective

Comparar proyectos desde mes 1 con stock, ventas, exposición, composición, áreas
relativas y precios observados sin fuga de información futura.

## Next action

Aplicar rama y ejecutar comandos en docs/EVOLUCION_COMERCIAL.md sobre Medallio local.
Verificar cobertura, proyectos sin inicio y unidades en revisión antes de consumir PBI.
No se ejecutó contra datos productivos ni se activaron tareas o Actions.

## Validation

16 aserciones SQL sobre PostgreSQL WASM/PGlite aprobadas, incluida instalación
idempotente. Python compilado. Pytest nativo omitido por falta de DSN descartable.

## Previous task

ABSORCION-NP-A-001 presente en main; verificación Medallio/Power BI permanece local.
