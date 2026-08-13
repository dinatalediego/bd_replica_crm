# OPEN DATA CONTRACT — producto/unidad

Para construir `analytics.fact_absorcion_detallada` con grain:

`fecha × proyecto × combinación existente de features`

faltan por demostrar físicamente los nombres/semántica histórica de:

- tipología
- subdivisión
- dormitorios
- piso
- tipo_unidad
- área
- precio
- descuento

No se inventan.

Ejecutar:

`sql/30_absorption_phase_c/09_discover_unit_product_features.sql`

Hasta resolverlo, la v0.1 entrega absorción correcta a grain:

`fecha × proyecto`.
