# Active Task

Task ID: ECONOMETRIA-DATASETS-001
Title: Datasets históricos y captura diaria para predicción comercial
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/datasets-econometricos
Base branch: main

## Objective

Implementar tablas y actualización para las siete recomendaciones econométricas,
con historia revisada separada de evidencia observada e integración al job local.

## Next action

Ejecutar scripts/67_install_econometric_datasets.ps1 en Medallio local y comprobar
status/cobertura. Guía: docs/DATASETS_ECONOMETRICOS.md. Incluye cambios de PR 48.

## Validation

19 tests Python aprobados. 23 aserciones SQL y tres controles de rechazo ejecutados
con PostgreSQL WASM/PGlite; instalación y reinstalación aprobadas.
PostgreSQL nativo omitido sin DSN descartable. Windows/Medallio real no accesibles.

## Limits

Tasas, inversión y ofertas/cierres sin evidencia quedan pendientes de importación;
visitas requieren etiquetas verificadas. No se inventa historia point-in-time.
Captura observada comienza al ejecutar localmente; programación preparada, no
instalada en el PC desde este entorno. Modelos existentes no se reentrenan aquí.
