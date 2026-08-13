# Modelo Power BI — Absorción v0.1

## Dimensiones PostgreSQL

### qDimPeriodoProyecto
Key: `codigo_proyecto`

### qDimFecha
Key: `fecha`

Marcar `qDimFecha` como tabla de fechas en Power BI.

## Relaciones de proyecto

`qDimPeriodoProyecto[codigo_proyecto]` 1 → * `qFactStockDiario[codigo_proyecto]`

`qDimPeriodoProyecto[codigo_proyecto]` 1 → * `qFactAbsorcionProyectoDiario[codigo_proyecto]`

`qDimPeriodoProyecto[codigo_proyecto]` 1 → * `qAggVentasMensual[codigo_proyecto]`

`qDimPeriodoProyecto[codigo_proyecto]` 1 → * `qFactVentasDetalle[codigo_proyecto]`

## Relaciones de fecha

`qDimFecha[fecha]` 1 → * `qFactStockDiario[fecha]` — activa

`qDimFecha[fecha]` 1 → * `qFactAbsorcionProyectoDiario[fecha]` — activa

`qDimFecha[fecha]` 1 → * `qFactVentasDetalle[fecha_venta]` — activa

Para `qAggVentasMensual`, relacionar:
`qDimFecha[fecha]` → `qAggVentasMensual[periodo_mes]`

Puede ser activa si el agregado mensual se usa en visuales separados.

Dirección:
single direction desde dimensiones a facts.

No relacionar hechos entre sí.

## Current views

`qAbsorcionCurrent` se usa para tarjetas de estado actual.
No requiere relación con fecha porque ya contiene solo la última fecha por proyecto.
Sí puede relacionarse por proyecto.
