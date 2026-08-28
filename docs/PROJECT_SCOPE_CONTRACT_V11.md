# Project Scope Contract v1.1

## Rule

Not every CRM project represents physical inventory.

Project `id=24`, name `Campañas`, is a lead-acquisition container. It must remain available for CRM attribution and lead analytics, but it is not a stock-bearing real-estate project.

## Governed semantics

`analytics.dim_proyecto_semantica` exposes:

- `proposito_proyecto`
- `flag_gestion_stock`
- `flag_absorcion`
- `motivo_exclusion_stock`

Current business rule:

- `id=24` → `CAPTACION_LEADS`, `flag_gestion_stock=false`, `flag_absorcion=false`.
- remaining projects → `INVENTARIO_COMERCIAL`, stock/absorption enabled.

## Consequences

`Campañas`:

- stays in `core.dim_proyecto` and its source unit remains auditable in `core.dim_unidad` / `analytics.dim_unidad_semantica`;
- is excluded from `fact_stock_snapshot_diario_unidad`;
- is excluded defensively from `fact_stock_ofertado_diario_tipo`;
- is excluded defensively from `fact_absorcion_proyecto_tipo_diario`;
- does not count in stock-completeness denominators;
- does not count as an unresolved `OTRO` product for the physical-stock contract.

This avoids deleting CRM/master data while preventing a lead-only technical project from becoming one unit of fictitious available stock.

## Evidence

Before this rule, the complete snapshot contained 3,237 unit records and the only remaining `OTRO` source type was `tipo_unidad_origen='proyecto'` with one row under project code `CAM`. The current-stock coverage report showed `CAM / OTRO` as one available unit with no ledger history. This is explained by the business purpose of project `Campañas`, not by missing inventory history.

After applying this rule, the expected eligible stock universe is 3,236 units. The prior global available-stock coverage gap of 528 should become 527; the one-unit reduction is a semantic exclusion, while the remaining 527 continue to represent genuine current-stock vs observed-ledger coverage gaps and must not be force-filled historically.
