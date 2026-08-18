# CORE Commercial Model v1

## Objetivo

Crear la primera capa `core` gobernada entre `raw_cygnus` y `analytics`, comenzando por dos entidades estables y reutilizables: proyecto y unidad.

## Objetos

- `core.dim_proyecto`: una fila por proyecto (`codigo_proyecto` único).
- `core.dim_unidad`: una fila por unidad (`codigo_unidad` único) y FK hacia proyecto.

## Semántica

Esta versión representa el **estado actual** observado en Sperant. No modela todavía historia de precios, stock, separaciones o ventas. Esa historia deberá implementarse posteriormente mediante hechos/snapshots temporales.

## Evidencia validada

Antes de construir CORE se verificó sobre `raw_cygnus`:

- 18 proyectos y 18 IDs únicos;
- 3,237 unidades y 3,237 IDs únicos;
- 0 códigos nulos o duplicados en proyecto/unidad;
- 0 unidades con `codigo_proyecto` nulo;
- 0 unidades huérfanas;
- reconciliación exacta de `proyectos.total_unidades` contra el conteo de unidades por proyecto.

## Ejecución

```powershell
python scripts/core_commercial.py refresh
python scripts/core_commercial.py status
```

Resultado validado localmente contra `medallio_dw`:

```text
raw_proyectos: 18
core_proyectos: 18
raw_unidades: 3237
core_unidades: 3237
proyectos_con_diferencia: 0
unidades_huerfanas: 0
```

Luego el Platform Command Center reconoce los diez schemas mínimos y PostgreSQL pasa de 83.3% (3/4) a 100% GREEN (4/4).

## Siguiente fase

Construir el primer hecho temporal gobernado, probablemente `core.fact_ciclo_comercial_unidad`, para modelar separaciones, anulaciones, ventas/minutas, stock y fechas efectivas sin mezclar historia con la dimensión de estado actual.
