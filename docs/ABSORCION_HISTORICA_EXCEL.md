# Absorción Histórica → Excel

Extensión del módulo mensual `60` dentro de `bd_replica_crm` / Medallio. Mantiene Medallio DW como **single source of truth** y convierte la historia observada del ledger en dos productos Excel complementarios.

## Los 3 outputs conviven

El reporte mensual existente **no se reemplaza**:

```powershell
scripts\60_exportar_movimiento_stock_mensual.bat 2026-09
```

Se agregan dos productos históricos:

```powershell
scripts\61_exportar_absorcion_historica_por_proyecto.bat
scripts\62_exportar_absorcion_historica_multiproyecto.bat
```

## Producto 1 — un Excel por proyecto

Ejemplo:

```text
Absorcion_Historica_Fénix_2026_09_09.xlsx
```

Estructura:

- `ACUMULADO`: matriz mensual desde el inicio comercial / primera evidencia hasta el último mes con stock observado.
- `YYYY-MM`: una pestaña por mes, con KPIs de absorción y detalle de movimientos de unidad.
- `CONTROL`: contrato, fechas y calidad de evidencia.

La pestaña `ACUMULADO` incluye:

- stock inicio;
- altas;
- separaciones;
- caídas;
- movimiento neto;
- vendidas / minutas;
- saldo final;
- absorción bruta mensual;
- absorción neta mensual;
- absorción neta 6 meses;
- stock ofertado acumulado;
- movimiento neto acumulado;
- vendidas / minutas acumuladas;
- absorción de stock acumulada;
- absorción neta de eventos acumulada;
- calidad/evidencia mensual.

Cada pestaña mensual muestra además:

- unidad;
- estado actual;
- piso;
- área;
- precio de lista actual;
- descuento vigente;
- precio con descuento;
- precio de venta actual para auditoría;
- proforma y fuente del evento.

## Producto 2 — Excel multiproyecto

Ejemplo:

```text
Absorcion_Historica_Multiproyecto_2026_09_09.xlsx
```

Estructura:

- `ACUMULADO`: resumen actual + matriz de absorción neta mensual por proyecto + matriz de absorción stock acumulada por proyecto.
- una pestaña por proyecto con toda su serie mensual y el detalle histórico de movimientos de unidad;
- `DATA_MENSUAL`: tabla larga consolidada proyecto × mes para análisis adicional.

## Alcance temporal

Por proyecto se toma:

1. `core.dim_proyecto.fecha_inicio_venta` como inicio comercial declarado cuando existe;
2. la primera evidencia observada en el ledger como inicio de medición real;
3. nunca se descarta un evento observado anterior a la fecha maestra: se conserva y se marca en `calidad_inicio`;
4. el reporte termina en el último mes con `stock_inicio_observado > 0`, `saldo_final_observado > 0` o altas de stock observadas.

Si la fecha de inicio comercial es anterior al primer evento observado, esos meses aparecen explícitamente como `SIN_EVIDENCIA_LEDGER`, con métricas en blanco. No se rellenan con ceros inventados.

## Definiciones de absorción

### Absorción neta mensual

```text
movimiento_neto_mes / stock_inicio_observado
```

con:

```text
movimiento_neto_mes = separaciones efectivas - caídas efectivas
```

### Absorción de stock acumulada

Mide qué proporción del stock observado acumulado ya no está disponible al cierre del mes:

```text
(stock_ofertado_acumulado - saldo_final_observado)
/ stock_ofertado_acumulado
```

Es la métrica acumulada principal para lectura de colocación de stock.

### Absorción neta de eventos acumulada

Se mantiene como segunda lectura para continuidad con el contrato de absorción:

```text
movimiento_neto_acumulado / stock_ofertado_acumulado
```

No se confunde con la absorción de stock acumulada.

## Contrato preservado

- scope principal: `DEPARTAMENTO`;
- sólo eventos con `transition_applied = true`;
- historia derivada de `analytics.fact_movimientos_stock`;
- no se fabrican fechas de entrada ni snapshots históricos;
- precio lista/descuento son valores **actuales** para contextualizar la unidad, no una reconstrucción histórica del precio de lista;
- `VENTA` / `MINUTA` se muestra separada de la separación neta;
- el reporte mensual `60` sigue disponible y sin cambios de contrato.

## Outputs

```text
output/
└── absorcion_historica/
    ├── por_proyecto/
    │   ├── Absorcion_Historica_Fénix_YYYY_MM_DD.xlsx
    │   ├── Absorcion_Historica_Tizón_y_Bueno_YYYY_MM_DD.xlsx
    │   └── Absorcion_Historica_Urbanzen_YYYY_MM_DD.xlsx
    └── multiproyecto/
        └── Absorcion_Historica_Multiproyecto_YYYY_MM_DD.xlsx
```

## CLI avanzado

Ambos productos:

```powershell
python scripts\absorption_history_export.py --mode both
```

Sólo un grupo de proyectos:

```powershell
python scripts\absorption_history_export.py --mode multi --projects Fénix Urbanzen
```

## Gate de validación

Antes de considerar un proyecto certificado para consumo gerencial:

1. comparar separaciones, caídas y ventas/minutas mensuales con el reporte comercial certificado;
2. revisar `calidad_inicio` y meses `SIN_EVIDENCIA_LEDGER`;
3. revisar que el último mes incluido corresponda al agotamiento/cierre del stock observado;
4. no convertir meses sin evidencia en ceros;
5. no interpretar los precios actuales de la unidad como precios históricos del mes del evento.
