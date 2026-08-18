# Commercial Lifecycle Discovery

## Objetivo

Antes de crear `core.fact_ciclo_comercial_unidad`, fijar con evidencia real:

1. granularidad de cada tabla fuente;
2. claves y duplicados;
3. nombres/estados de los eventos comerciales;
4. columnas realmente disponibles para proforma, separación, anulación y venta;
5. contratos de unión entre unidad, proforma, cliente y proceso.

## Fuentes inspeccionadas

- `raw_cygnus.clientes`
- `raw_cygnus.clientes_proyectos`
- `raw_cygnus.proformas`
- `raw_cygnus.proforma_unidad`
- `raw_cygnus.procesos`
- `raw_cygnus.unidades`

## Ejecución

```powershell
python scripts/discover_commercial_lifecycle.py
```

Genera:

- `reports/commercial_lifecycle_columns.csv`
- `reports/commercial_lifecycle_table_profile.csv`
- `reports/commercial_lifecycle_value_profile.csv`

## Gate de diseño

No crear aún la fact final solo porque existan columnas compatibles. Primero debe quedar explícito:

- cuál es la fila de negocio de la fact;
- cómo se identifica un ciclo comercial;
- qué evento gobierna separación;
- qué evento gobierna venta/minuta;
- cómo se representan anulaciones repetidas;
- cómo se conserva la fecha RAW frente a fechas analíticas corregidas;
- cómo se vinculan múltiples unidades a una misma proforma;
- cómo se excluyen excepciones de negocio sin borrar el RAW.

## Diseño esperado después del discovery

```text
raw_cygnus.proformas
          |
raw_cygnus.proforma_unidad ----+
          |                     |
raw_cygnus.procesos ------------+--> core.fact_ciclo_comercial_unidad
          |                     |
core.dim_unidad ----------------+
          |
core.dim_proyecto --------------+
```

La fact debe ser temporal y auditable. `core.dim_unidad` continúa representando el estado actual; no se sobrecarga con historia comercial.
