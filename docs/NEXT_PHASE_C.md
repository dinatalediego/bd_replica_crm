# Próxima Fase C

Una vez validados:

- `int_unidad_entrada_stock`
- `int_proforma_minuta`
- `int_ciclo_comercial_unidad`
- `fact_movimientos_stock`

la siguiente entrega construirá:

1. `analytics.fact_ventas_detalle`
2. `analytics.agg_ventas_mensual`
3. `analytics.dim_periodo_comercial_proyecto`
4. `analytics.fact_stock_ofertado_diario`
5. `analytics.fact_absorcion_detallada`

El snapshot diario NO utilizará `unidades × calendario`.
Se derivará del ledger por eventos y ventanas/acumulados.

Después:

`features.absorcion_features_diarias`
→ forecast
→ riesgo de stock
→ pricing
→ Power BI de Absorción.
