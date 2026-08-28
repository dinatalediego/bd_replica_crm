# Absorption Scope Contract v1.1

## Purpose

Preserve the complete commercial stock universe while preventing unlike unit products from contaminating each other's absorption metrics.

The contract explicitly separates two questions that must not be conflated:

1. **What is the complete current stock?** — certified from the current unit dimension and persisted as daily snapshots.
2. **What historical stock transitions have been observed?** — event-sourced from `analytics.fact_movimientos_stock`.

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

`analytics.dim_unidad_semantica` combines the stable CORE product classification with the canonical current inventory state from `analytics.v_inventory_state_current`, falling back to current source labels when the event ledger does not contain the unit.

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

## Current stock contract

`analytics.fact_stock_snapshot_diario_unidad` is the certified current-state stock snapshot with grain:

`fecha_snapshot × codigo_unidad`

Every refresh replaces only the current day's snapshot and therefore starts accumulating point-in-time stock evidence without inventing historical entry dates.

`analytics.v_stock_consolidado_actual_por_tipo` aggregates the latest complete snapshot by:

`codigo_proyecto × tipo_unidad_consolidado`

It preserves the compatibility columns:

- `stock_fin` = current available units.
- `separadas_activas` = current separated units.
- `vendidas_acumuladas` = current sold units.

and adds blocked/other state counts and the total unit universe.

## Historical / temporal rule

Current-state booleans must not be back-cast to reconstruct historical stock.

Historical movements remain event-sourced from `analytics.fact_movimientos_stock`. The historical typed layer is:

- `analytics.fact_stock_ofertado_diario_tipo`
- `analytics.fact_absorcion_proyecto_tipo_diario`

The current implementation of the event ledger creates `ALTA_STOCK` from the first observed `proforma_unidad`. This is useful evidence but is **not a complete historical stock-entry contract** for units that have never been proformed.

For that reason the historical absorption metrics are explicitly interpreted as **observed-ledger absorption** until historical stock entry is demonstrated or enough certified daily snapshots accumulate.

No project-start date is silently imputed to missing units.

## Coverage / reconciliation layer

`analytics.v_stock_ledger_actual_por_tipo` preserves the latest event-ledger stock state.

`analytics.v_stock_coverage_actual_por_tipo` compares, by project and governed product type:

- complete current available stock vs ledger available stock;
- current separated stock vs ledger separated stock;
- current sold stock vs ledger sold stock;
- coverage ratio and explicit gaps.

`analytics.v_absorcion_principal_estado_actual` combines latest department absorption with current stock coverage so consumers can distinguish:

- `CERTIFICADO_ESTADO_ACTUAL`
- `HISTORICO_LEDGER_CON_GAP_DE_COBERTURA`

## Absorption scopes

### Primary business absorption

`analytics.v_absorcion_principal_proyecto_diario`

Scope: `tipo_unidad_consolidado='DEPARTAMENTO'`.

This is the default project-level apartment absorption series, but its historical denominator remains an observed-ledger denominator while current-stock coverage gaps exist.

For operational use prefer `analytics.v_absorcion_principal_estado_actual`, which carries the coverage diagnosis with the metric.

### Complementary absorption

Dedicated views exist for:

- `analytics.v_absorcion_estacionamientos_diario`
- `analytics.v_absorcion_depositos_diario`
- `analytics.v_absorcion_locales_diario`
- `analytics.v_absorcion_otros_diario`

These metrics are valid independently but must not be summed into apartment absorption rates.

### Consolidated complete stock

The complete current stock is `analytics.fact_stock_snapshot_diario_unidad` / `analytics.v_stock_consolidado_actual_por_tipo`.

The historical observed stock is `analytics.fact_stock_ofertado_diario_tipo`.

The distinction is intentional.

## Metric definitions

For each project + product type independently:

- gross observed absorption = effective separations / ledger-observed available stock at start of window.
- net observed absorption = (effective separations - effective falls/reentries) / ledger-observed available stock at start of window.
- current available stock = complete snapshot from the unit dimension.
- sales/minutes in the current Phase C physical vocabulary remain `ventas`; business-facing models should label the reconciled measure as `minutas_canonicas` until the physical column is renamed in a versioned migration.

## Reconciliation evidence that motivated v1.1

### Event-scope breach

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

### Current-stock coverage breach discovered after v1.1 execution

The first local execution produced:

- semantic unit universe: **3,237** units.
- current states: **1,699 available**, **293 separated**, **1,245 sold**.
- event-ledger latest state: **1,171 available**, **293 separated**, **1,245 sold**.
- available units absent from the event-ledger stock: **528**.

Thus separated and sold states reconcile exactly, while available-stock history is incomplete. The observed ledger currently covers about **68.9%** of complete current available stock (`1,171 / 1,699`).

This finding is consistent with the existing Phase A warning that the initial stock date had not yet been demonstrated. Units with no first `proforma_unidad` event can be present and available in `core.dim_unidad` while absent from the historical `ALTA_STOCK` ledger.

The correction is not to fabricate historical entry dates. v1.1 now certifies current stock independently, stores daily snapshots going forward, and exposes the ledger coverage gap explicitly.

## Classification evidence

The same execution classified the current 3,237-unit universe as:

- `DEPARTAMENTO`: 1,962
- `ESTACIONAMIENTO`: 1,126
- `DEPOSITO`: 143
- `LOCAL`: 5
- `OTRO`: 1

Current commercial-state classification had zero `OTRO` states:

- `DISPONIBLE`: 1,699
- `SEPARADO`: 293
- `VENDIDO`: 1,245

`BLOQUEADO` remains part of the governed contract even though no units were classified as blocked in this execution.

The single `OTRO` product type remains an explicit review item; it must not be guessed into another class without inspecting its source type.

## Gates before promotion

1. Ledger-vs-type event reconstruction must return zero rows.
2. Current snapshot count must equal `core.dim_unidad` count.
3. Review the single `OTRO` source product type.
4. Current-state `OTRO` values must remain zero or be explicitly mapped.
5. Current stock-vs-ledger gaps must be visible through `v_stock_coverage_actual_por_tipo`; they are not a reason to fabricate history.
6. Compare primary apartment separations/minutes/falls against business-certified monthly totals.
7. Do not alter `transition_applied` rules solely to force totals to match. Resolve each exception at source/cycle level.
8. If a residential subtype has `fecha_de_minuta` but Phase B does not propagate it, update Phase B only after the exception is demonstrated.
9. Promote a fully historical **certified** absorption denominator only when historical stock entry is demonstrated or when sufficient certified snapshot history exists for the required window (for example 30 daily snapshots for a 30-day denominator).

## Source strategy

The semantic contract is source-agnostic. `raw_cygnus` and future/parallel `raw_mercado` adapters should map unit records into the same governed product and state semantics before analytics consumption. Source-specific text/status conventions must not leak into absorption facts or Power BI measures.
