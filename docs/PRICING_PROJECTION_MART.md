# Pricing Projection Mart — Medallio

## Decisión de arquitectura

Las cuatro consultas Power BI originales:

- `Base_Proyeccion_Tipologia`
- `Supuestos_Absorcion`
- `Hitos_Pricing`
- `Fact_Proyeccion_Pricing`

dejan de contener la lógica principal del simulador. Power BI pasa a ser consumidor; Medallio pasa a gobernar inputs, cálculo, QA y refresco.

No se reutilizó `analytics.fact_absorcion_*` ni `analytics.v_stock_disponible_export` como sustitutos porque representan hechos/estado observados. Los valores entregados en el M son **supuestos de simulación** y mezclarlos con stock observado cambiaría la semántica.

## Objetos

### Inputs controlados

`pricing.projection_baseline_assumption`

Grano: proyecto × tipo_unidad × nombre_tipologia × tipologia_ubicacion.

Contiene solamente inputs: stock baseline, precio/m² baseline, área, descuento, ventas/mes, horizonte y fecha de inicio. Los campos derivados no se duplican.

`pricing.absorption_scenario`

Grano: escenario × tramo.

`pricing.price_milestone`

Grano: proyecto × tipo_unidad × nombre_tipologia × hito.

### Vistas Power BI

- `analytics.v_base_proyeccion_tipologia`
- `analytics.v_supuestos_absorcion`
- `analytics.v_hitos_pricing`

### Fact

`analytics.fact_proyeccion_pricing`

Grano:

```text
proyecto
× tipo_unidad
× nombre_tipologia
× tipologia_ubicacion
× escenario
× mes_n
```

El cálculo preserva la semántica del M:

```text
ventas_teoricas = ventas_mes_base × factor_tramo
ventas_mes       = min(stock_inicial, ventas_teoricas)
stock_final      = max(0, stock_inicial - ventas_mes)

activar hito si:
mes_n >= mes_hito
OR pct_vendido_acumulado >= pct_vendido_objetivo

precio_m2_vigente = precio_m2_base + aumento_acumulado
precio_unitario    = precio_m2_vigente × area × (1 - descuento)
ingreso_mes        = ventas_mes × precio_unitario
```

El ingreso acumulado se calcula secuencialmente en PostgreSQL, eliminando el segundo `Table.Group + List.FirstN` que necesitaba el M original.

Además, Medallio conserva `flag_hito_4_activado`, que el M calculaba pero omitía en el último Expand.

## Refresco

`scripts/run_hourly.bat` ejecuta automáticamente:

```text
RAW
→ schema sync
→ CORE
→ analytics
→ absorption/lifecycle
→ pricing projection
→ materialized views
→ observability
```

El paso de pricing llama:

```text
scripts/refresh_pricing_projection.py
```

y valida `pricing.v_projection_health`.

## Seed inicial

Se migraron únicamente las filas **activas** del M entregado.

La base activa contiene Torre Marsano M1–M13. Los bloques de Torre Nápoles que estaban comentados en `Base_Proyeccion_Tipologia` se consideran legacy y no se activan automáticamente.

`Hitos_Pricing` sí conserva el hito activo de Torre Nápoles Tipología 2 porque estaba fuera de comentarios. No genera proyección mientras no exista un baseline activo correspondiente.

## Moneda: deuda semántica explícita

El M original suma `aumento_usd_m2` directamente a `precio_m2_base`. Para Torre Marsano los valores de `precio_m2_base` parecen tener una escala distinta a Torre Nápoles, pero la fuente no declara moneda/tipo de cambio en estas tres consultas.

Medallio preserva los números para mantener compatibilidad; **no normaliza moneda silenciosamente**. Antes de usar la simulación como regla real de pricing, debe definirse la unidad monetaria por proyecto y la política de tipo de cambio.

## Power BI

Mantén los nombres de las consultas existentes para no romper medidas/relaciones y reemplaza su Editor avanzado por los conectores versionados en `powerbi/M`.

Así, `Fact_Proyeccion_Pricing` deja de ejecutar ~500 líneas de M y solo carga la tabla ya calculada por PostgreSQL.
