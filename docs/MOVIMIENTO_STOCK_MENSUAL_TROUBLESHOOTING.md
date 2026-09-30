# Troubleshooting · Movimiento de Stock Mensual

## Error: faltan `fact_stock_ofertado_diario_tipo`, `dim_unidad_semantica` o `v_stock_coverage_actual_por_tipo`

Ese error correspondía al preflight inicial del módulo, que exigía materializaciones de Phase C / absorción v1.1 aunque el reporte mensual podía derivarse de forma segura desde el ledger ya existente.

La versión corregida usa como dependencias obligatorias únicamente:

- `core.dim_unidad`
- `core.dim_proyecto`
- `analytics.fact_movimientos_stock`
- `analytics.stock_discount_rules`

El histórico mensual se reconstruye en una **vista read-only** desde `fact_movimientos_stock`, filtrando `transition_applied=true` y sólo unidades cuyo `tipo_unidad` pertenece al scope `DEPARTAMENTO`.

`analytics.v_stock_coverage_actual_por_tipo` pasa a ser opcional. Si existe, se incorpora a la hoja `CONTROL`; si no existe, el Excel se genera igual y declara explícitamente:

`HISTORICO_LEDGER_OBSERVADO_SIN_SNAPSHOT_CERTIFICADO`

No se ejecutan procedimientos con `TRUNCATE`, no se fabrican snapshots y no se back-castean estados actuales.

## Reejecución

Después de actualizar la rama:

```powershell
git pull origin feat/monthly-stock-movement-export
scripts\60_exportar_movimiento_stock_mensual.bat 2026-09
```

El paso `[1/2]` debe validar sólo las dependencias mínimas y luego instalar las dos vistas del módulo.
