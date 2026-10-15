# MEDALLIO — Absorption Mart / Fase C Core v0.1.0

Prerequisito:
- Fase B v0.1 instalada.
- Fase B v0.2 Reconciliation instalada.
- `analytics.v_ciclo_comercial_reconciliado` disponible.
- `analytics.fact_movimientos_stock` validada.

## Objetivo

Construir en PostgreSQL el primer mart consumible por Power BI:

- `analytics.fact_ventas_detalle`
- `analytics.agg_ventas_mensual`
- `analytics.dim_periodo_comercial_proyecto`
- `analytics.fact_stock_ofertado_diario`
- `analytics.fact_absorcion_proyecto_diario`

La tabla `fact_absorcion_detallada` por tipología/subdivisión/dormitorios/piso
se reserva para v0.2, después de validar físicamente las columnas de producto
de `raw_cygnus.unidades`.

No se inventan columnas de features.

## Principio de negocio

### Stock

Proviene exclusivamente de transiciones físicas efectivas:

`fact_movimientos_stock.transition_applied = true`

### Venta canónica

Proviene de:

`analytics.v_ciclo_comercial_reconciliado`

con:

- `resultado_canonico = 'VENTA'`
- `fecha_venta_validada IS NOT NULL`
- `reconciliation_status = 'RECONCILED'`

Los 4 errores temporales y los 9 casos Venta/Caída mismo día NO ingresan al
mart canónico hasta resolverlos.

### Absorción

La v0.1 conserva siempre:
- numerador;
- denominador;
- ventana temporal.

Implementa tasas de salida de inventario:

- absorcion_bruta_30d = separaciones_brutas_30d / stock_inicio_ventana_30d
- absorcion_neta_30d = separaciones_netas_30d / stock_inicio_ventana_30d

y análogos 7d/90d.

Estas definiciones quedan explícitas en `analytics.metric_definitions`.

### Meses de stock

`meses_stock_ventas_30d = stock_fin / ventas_30d`

porque `ventas_30d` representa aproximadamente un mes de velocidad observada.

Si `ventas_30d = 0`, devuelve NULL; no se inventa infinito.

## Power BI

Power BI consume:
- ventas detalle;
- agregado mensual;
- stock diario;
- absorción diaria por proyecto;
- periodo comercial;
- reconciliación.

No reconstruye stock ni reglas de venta.


## Seguridad adicional

Antes del backfill, Fase C valida que una misma `codigo_unidad` no tenga
movimientos físicos efectivos en más de un `codigo_proyecto`.

Si existen, el backfill se detiene y se declara OPEN BUSINESS RULE, porque
agregar stock por proyecto sin resolver esa temporalidad podría crear stock
positivo en un proyecto y negativo en otro.

## Incrementalidad

v0.1 es un backfill controlado para validar el mart.

NO debe programarse `TRUNCATE + INSERT` cada hora.

La Fase D implementará recalculation windows por proyecto/fecha mínima afectada
después de validar los resultados reales de esta fase.


## Forecasting comercial con evidencia

Piloto adicional: promedio reciente, ETS, GMM con análogos y Random Forest, evaluación temporal, snapshots/predicciones append-only y seguimiento de acciones. [Guía de ejecución y límites](docs/COMMERCIAL_FORECASTING.md). Demo: `scripts/63_forecasting_demo.bat`; Medallio: `scripts/64_forecasting_medallio.bat`. [Notebook de exposición](notebooks/11_commercial_forecasting_evidence.ipynb). Sin carga adicional a Redshift ni promoción automática.

## Escenarios monetarios de impacto ML

Importación local y versionada del Excel agregado de metas, colocado y stock;
vistas por proyecto/portafolio para tres sensibilidades y comparación adicional
excluyendo stock bloqueado. Son hipótesis económicas, no ventas causadas por ML.
[Contrato, controles y pasos para VS Code](docs/ML_IMPACT_SCENARIOS.md).

[Guía de Power BI para cobertura, pronóstico y resultados maduros](docs/COMMERCIAL_FORECASTING_POWERBI.md). [Arquitectura de robustez v2](docs/COMMERCIAL_FORECASTING_ROBUSTNESS.md).

## Productos analíticos portables para Atlas

La capa opcional [Medallio → Atlas](docs/publishing/README.md) produce Data,
Model, Story y Scenario Packs versionados, con una demo sintética offline y
registro privado de evidencia. No modifica la réplica ni la programación horaria.
