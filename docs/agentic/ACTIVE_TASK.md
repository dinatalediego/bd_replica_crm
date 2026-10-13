# Active Task

Task ID: MODEL-DATA-QUALITY-001
Title: Fiscalización de calidad para datasets predictivos de Medallio
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/model-data-quality-gates
Base branch: main

## Objetivo

Crear controles repetibles para forecast comercial, riesgo de caída de separación y ventas proyecto-mes. Mantener calidad de datos, disponibilidad de outcomes y rendimiento predictivo como estados distintos.

## Implementado

- Catálogo SQL de pruebas, resultados agregados por corrida, vista del último gate y manifiesto reproducible sin filas fuente ni PII.
- Runner local con estados PASS/WARN/BLOCK, cobertura de benchmark, trazabilidad, maduración, fuga temporal, grano, allowlist de features, soporte por clase, reconciliación mensual, mes parcial y unidades en revisión. Una cuarta suite audita presencia/sintaxis del código y deja visible el trainer supervisado de riesgo que falta.
- Guía de estrategia por decisión económica y ejecución en worktree local.
- El componente es opt-in y se instala con schema_sync. No carga datos en Supabase, no modifica ventas o forecasts y no promociona modelos.

## Validación

py_compile y 7 pruebas unitarias nuevas pasaron en el entorno de trabajo. No se ejecutó una conexión a PostgreSQL Medallio desde este entorno. El smoke test de las vistas y umbrales reales queda para el PC local.

## Siguiente acción

En un worktree separado, aplicar python scripts/schema_sync.py --only model_data_quality_gates, correr las pruebas y luego python scripts/model_data_quality_gates.py run y status. Revisar resultados y manifiestos en las vistas documentadas en docs/MODEL_DATA_QUALITY_GATES.md. WAPE seguirá N/A hasta que el gate de maduración enlace outcomes prospectivos suficientes.
