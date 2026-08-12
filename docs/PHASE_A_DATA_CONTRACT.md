# Fase A — Data Contract preliminar

## Modelo conceptual
- Evento comercial: fuente esperada `raw_cygnus.procesos`.
- Source key del evento: `procesos.id`.
- Business key inicial del ciclo a validar: `codigo_proforma + codigo_unidad`.
- `proformas 1:N proforma_unidad N:1 unidades` debe demostrarse.
- `fecha_venta` futura: `fecha_de_minuta`; fallback a `fecha_firma_legacy` solo para separaciones pre-2026; si no, NULL.
- Inventario futuro: AVAILABLE → SEPARATED → SOLD; Anulación válida: SEPARATED → AVAILABLE.
- Anulación redundante conserva auditoría pero no genera +1 de stock.

## Grains futuros a validar
| Dataset | Grain |
|---|---|
| int_proforma_minuta | proforma + unidad aplicable |
| int_ciclo_comercial_unidad | 1 ciclo de una unidad dentro de una proforma |
| fact_movimientos_stock | 1 evento relevante de inventario |
| fact_ventas_detalle | 1 unidad dentro de 1 ciclo |
| fact_stock_ofertado_diario | fecha × proyecto × combinación existente |
| fact_absorcion_detallada | fecha × proyecto × combinación existente |

## Riesgos
- `codigo_proforma` agrupa múltiples unidades.
- pueden existir múltiples separaciones por proforma-unidad.
- `datos_extras` puede no estar replicada aún.
- `fecha_de_minuta` puede ser texto/múltiple.
- varias anulaciones no equivalen a varios reingresos.
- `Venta.fecha_inicio` no es universal desde 2026.
- atributos actuales pueden romper point-in-time correctness.
- fecha inicial de stock aún no demostrada.
