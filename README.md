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
