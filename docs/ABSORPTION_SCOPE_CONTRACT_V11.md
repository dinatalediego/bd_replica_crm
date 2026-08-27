# Absorption Scope Contract v1.1

## Purpose

Preserve the complete commercial stock universe while preventing unlike unit products from contaminating each other's absorption metrics.

## Governed product semantics

Stable product semantics are promoted to `core.dim_unidad`:

- `tipo_unidad_consolidado`
- `flag_departamento`
- `flag_estacionamiento`
- `flag_deposito`
- `flag_local`

Canonical values:

- `DEPARTAMENTO`
- `ESTACIONAMIENTO`
- `DEPOSITO`
- `LOCAL`
- `OTRO`

The rule intentionally classifies any source type containing `departamento` as `DEPARTAMENTO`; this includes flat, duplex, triplex or later residential subtypes without enumerating each subtype in downstream analytics.

## Governed current-state semantics

`analytics.dim_unidad_semantica` combines the stable CORE product classification with the canonical current inventory state from `analytics.v_inventory_state_current`.

Columns exposed for BI / DS consumption:

- `flag_disponible`
- `flag_bloqueado`
- `flag_estado_separado`
- `flag_vendido`
- `flag_otro_estado`
- `estado_comercial_consolidado`
- `orden_estado`

Ordering contract:

1. `DISPONIBLE`
2. `BLOQUEADO`
3. `SEPARADO`
4. `VENDIDO`
99. `OTRO`

Canonical inventory state has precedence over free-text current-state labels. Source labels remain available for audit.

## Temporal rule

Current-state booleans must not be used to reconstruct historical stock. Historical stock remains event-sourced from `analytics.fact_movimientos_stock`.

Therefore:

- `core.dim_unidad` = current master/product semantics.
- `analytics.dim_unidad_semantica` = current semantic state for BI/selection.
- `analytics.fact_movimientos_stock` = historical source of truth for state transitions.
- `analytics.fact_stock_ofertado_diario_tipo` = historical stock by governed product class.
- `analytics.fact_absorcion_proyecto_tipo_diario` = absorption by governed product class.

## Absorption scopes

### Primary business absorption

`analytics.v_absorcion_principal_proyecto_diario`

Scope: `tipo_unidad_consolidado='DEPARTAMENTO'`.

This is the default source for project-level apartment absorption, pricing, stock-risk and Power BI commercial analysis.

### Complementary absorption

Dedicated views exist for:

- `analytics.v_absorcion_estacionamientos_diario`
- `analytics.v_absorcion_depositos_diario`
- `analytics.v_absorcion_locales_diario`
- `analytics.v_absorcion_otros_diario`

These metrics are valid independently but must not be summed into apartment absorption rates.

### Consolidated stock

`analytics.fact_stock_ofertado_diario_tipo` preserves all stock and distinguishes product type in the grain:

`fecha × codigo_proyecto × tipo_unidad_consolidado`

`analytics.v_stock_consolidado_actual_por_tipo` exposes the latest stock by type.

## Metric definitions

For each project + product type independently:

- gross absorption = effective separations / available stock at start of window.
- net absorption = (effective separations - effective falls/reentries) / available stock at start of window.
- sales/minutes in the current Phase C vocabulary remain `ventas`; business-facing models should label the reconciled measure as `minutas_canonicas` until the physical column is renamed in a versioned migration.

## Reconciliation evidence that motivated v1.1

August 2026 validation showed:

- effective apartment separations: 36.
- mixed existing aggregate separations: 45.
- difference attributable to non-apartment unit events: 9.
- effective apartment falls: 6.
- mixed existing aggregate falls: 7.
- difference attributable to non-apartment unit events: 1.
- apartment canonical minutes: 5.
- apartment ledger sales/minutes: 5.

Additionally, cycle-level apartment separations were 40 while effective ledger separations were 36. The four-event difference is not automatically an error: the governed numerator remains effective physical transitions (`transition_applied=true`). Exceptions must be inspected rather than force-counted.

## Gates before promotion

1. `02_validation.sql` must return zero rows for ledger-vs-type reconstruction gaps.
2. Review all `OTRO` source product types before treating coverage as complete.
3. Review all `OTRO` commercial states before treating boolean state coverage as complete.
4. Compare primary apartment metrics against business-certified monthly totals.
5. Do not alter `transition_applied` rules solely to force totals to match. Resolve each exception at source/cycle level.
6. If a residential subtype has `fecha_de_minuta` but Phase B does not propagate it, update Phase B only after the exception is demonstrated. This avoids broadening the existing minute rule without evidence.

## Source strategy

The semantic contract is source-agnostic. `raw_cygnus` and future/parallel `raw_mercado` adapters should map their unit records into the same governed product classes before analytics consumption. Source-specific text/status conventions must not leak into absorption facts or Power BI measures.
