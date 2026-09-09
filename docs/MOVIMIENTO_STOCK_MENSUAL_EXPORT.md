# Movimiento de Stock Mensual → Excel

Módulo de reporting dentro de `bd_replica_crm` / Medallio. No crea una fuente paralela: Medallio DW sigue siendo el **single source of truth** y Excel es sólo una capa de presentación.

## Objetivo

Generar un Excel ejecutivo mensual parecido al formato comercial usado por Cygnus, con:

- stock observado al inicio del mes;
- movimiento neto del mes;
- ventas/minutas del mes;
- saldo final observado;
- absorción neta del mes;
- absorción neta de los últimos 6 meses;
- detalle por proyecto de las unidades que tuvieron movimientos efectivos;
- precio de lista actual, descuento comercial vigente y precio con descuento;
- hoja de control con cobertura y calidad del histórico.

## Contrato semántico preservado

Este módulo **no redefine absorción**. Consume el contrato existente `ABSORPTION_SCOPE_CONTRACT_V11.md`.

### Scope principal

`DEPARTAMENTO` únicamente.

Estacionamientos, depósitos, locales y otros productos no se mezclan con la absorción principal del proyecto.

### Stock histórico

Fuente:

- `analytics.fact_stock_ofertado_diario_tipo`
- reconstruida desde `analytics.fact_movimientos_stock`

Por contrato, es **histórico observado por ledger**. No se fabrican fechas de entrada de stock para unidades sin evidencia histórica.

### Stock actual

La certificación actual continúa en:

- `analytics.fact_stock_snapshot_diario_unidad`
- `analytics.v_stock_consolidado_actual_por_tipo`

La cobertura entre estado actual certificado e histórico observado se conserva en:

- `analytics.v_stock_coverage_actual_por_tipo`

### Movimiento neto

`separaciones efectivas - caídas efectivas`

Este es el numerador de la absorción neta gobernada.

### Ventas / minutas

Las ventas/minutas se muestran **separadas** del movimiento neto. No se sustituyen entre sí.

En el vocabulario físico actual de Phase C, `ventas` corresponde a la medida reconciliada que debe leerse comercialmente como `minutas_canonicas` hasta una migración versionada del nombre físico.

### Absorción mensual

`movimiento_neto_mes / stock_inicio_observado`

### Absorción últimos 6 meses

Suma del movimiento neto de los 6 meses calendario hasta el mes reportado dividida por el stock observado al inicio de la ventana. Si no existen 6 meses observados, el Excel deja la celda vacía en vez de inventar historia.

## Precios

El detalle por unidad usa:

- `core.dim_unidad.precio_lista_actual`
- `analytics.stock_discount_rules.discount_pct`
- `precio_con_descuento = precio_lista_actual * (1 - discount_pct)`

Estos son precios **actuales** de la unidad y reglas comerciales vigentes. El módulo también conserva `precio_venta_actual` en la vista analítica para auditoría, pero no lo presenta como si fuera precio histórico de lista.

## Objetos nuevos

### SQL

`sql/60_monthly_stock_movement/00_monthly_stock_movement.sql`

Crea:

- `analytics.v_stock_movimiento_mensual_export`
- `analytics.v_stock_movimiento_mensual_unidad_export`

### Python

`src/replica_cygnus/monthly_stock_export/`

Genera el workbook y valida dependencias sin reconstruir ni truncar la capa de absorción.

### CLI

```powershell
python scripts/monthly_stock_movement_export.py --install-view --month 2026-09
```

### BAT

Mes actual:

```powershell
scripts\60_exportar_movimiento_stock_mensual.bat
```

Mes específico:

```powershell
scripts\60_exportar_movimiento_stock_mensual.bat 2026-08
```

## Output

```text
output/
└── movimiento_stock_mensual/
    └── Movimiento_Stock_2026_09.xlsx
```

## Estructura del Excel

### RESUMEN

- PROYECTO
- STOCK AL cierre del mes anterior
- MOVIMIENTO NETO DEL MES
- VENDIDAS / MINUTAS DEL MES
- SALDO FINAL
- ABSORCIÓN NETA % DEL MES
- ABSORCIÓN NETA ÚLTIMOS 6 MESES

### Hojas por proyecto

Incluyen KPIs superiores y detalle de movimientos:

- MOVIMIENTO
- FECHA
- UNIDAD
- ESTADO ACTUAL
- PISO
- ÁREA M²
- PRECIO LISTA
- DSCTO.
- PRECIO CON DESCUENTO

Movimientos coloreados:

- `SEPARACION`: naranja suave
- `CAIDA`: rojo suave
- `VENTA`: verde suave

### CONTROL

Expone:

- cobertura de stock actual vs ledger;
- gap de stock disponible;
- calidad del histórico;
- método del stock histórico;
- método del movimiento.

## Dependencias

El módulo no ejecuta automáticamente procedimientos que reconstruyen o truncan hechos de absorción. Antes de instalar sus vistas valida la existencia de:

- `core.dim_unidad`
- `core.dim_proyecto`
- `analytics.fact_movimientos_stock`
- `analytics.fact_stock_ofertado_diario_tipo`
- `analytics.dim_unidad_semantica`
- `analytics.v_stock_coverage_actual_por_tipo`
- `analytics.stock_discount_rules`

Si falta una dependencia, el proceso se detiene con un mensaje explícito. Esto evita modificar el DW silenciosamente.

## Gate de validación recomendado

Antes de compartir un reporte mensual:

1. comparar `ventas_minutas_mes` con el total comercial certificado del mes;
2. comparar separaciones y caídas efectivas con el reporte comercial;
3. revisar `CONTROL.calidad_stock_historico` y cobertura;
4. confirmar que el periodo solicitado tiene evidencia suficiente;
5. no alterar `transition_applied` sólo para forzar coincidencias.
