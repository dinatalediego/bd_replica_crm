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

Este módulo **no redefine absorción**. Respeta `ABSORPTION_SCOPE_CONTRACT_V11.md`, pero puede ejecutarse aunque las tablas materializadas de Phase C / v1.1 todavía no estén instaladas en PostgreSQL local.

### Scope principal

`DEPARTAMENTO` únicamente.

Estacionamientos, depósitos, locales y otros productos no se mezclan con la absorción principal del proyecto.

### Stock histórico

La vista mensual se deriva directamente de:

- `analytics.fact_movimientos_stock`
- `core.dim_unidad`

Sólo se aplican eventos con `transition_applied=true`.

El stock diario observado se reconstruye como suma acumulada de `delta_stock` por proyecto, sin persistir ni truncar hechos intermedios. Esto es equivalente conceptualmente a la capa `fact_stock_ofertado_diario_tipo` para el scope DEPARTAMENTO, pero permite que el reporte funcione cuando esa materialización no existe localmente.

Por contrato, sigue siendo **histórico observado por ledger**. No se fabrican fechas de entrada de stock para unidades sin evidencia histórica.

### Stock actual y cobertura

Si existe `analytics.v_stock_coverage_actual_por_tipo`, el Excel incorpora en `CONTROL`:

- cobertura del stock actual;
- gap de stock disponible;
- calidad de reconciliación.

Si esa vista no existe, el reporte **no falla**. La cobertura queda vacía y la calidad se etiqueta como:

`HISTORICO_LEDGER_OBSERVADO_SIN_SNAPSHOT_CERTIFICADO`

La ausencia de snapshot certificado no se oculta ni se reemplaza por una reconstrucción inventada.

### Movimiento neto

`separaciones efectivas - caídas efectivas`

Este es el numerador de la absorción neta gobernada.

### Ventas / minutas

Las ventas/minutas se muestran **separadas** del movimiento neto. No se sustituyen entre sí.

En el vocabulario físico actual, `VENTA` corresponde al evento efectivo que comercialmente debe interpretarse como venta/minuta reconciliada según el contrato vigente.

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

Genera el workbook, valida sólo dependencias mínimas y consulta cobertura actual únicamente cuando está disponible.

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

- cobertura de stock actual vs ledger, cuando existe;
- gap de stock disponible, cuando existe;
- calidad del histórico;
- método del stock histórico;
- método del movimiento.

## Dependencias

Dependencias mínimas obligatorias:

- `core.dim_unidad`
- `core.dim_proyecto`
- `analytics.fact_movimientos_stock`
- `analytics.stock_discount_rules`

Dependencia opcional de calidad:

- `analytics.v_stock_coverage_actual_por_tipo`

El módulo **no requiere** para ejecutarse:

- `analytics.fact_stock_ofertado_diario_tipo`
- `analytics.dim_unidad_semantica`
- `analytics.fact_stock_snapshot_diario_unidad`

Tampoco ejecuta procedimientos que hagan `TRUNCATE` o reconstruyan Phase C. Esto mantiene el reporte como consumidor de Medallio, no como dueño de la capa histórica.

## Gate de validación recomendado

Antes de compartir un reporte mensual:

1. comparar `ventas_minutas_mes` con el total comercial certificado del mes;
2. comparar separaciones y caídas efectivas con el reporte comercial;
3. revisar `CONTROL.calidad_stock_historico` y cobertura si existe;
4. confirmar que el periodo solicitado tiene evidencia suficiente;
5. no alterar `transition_applied` sólo para forzar coincidencias.
