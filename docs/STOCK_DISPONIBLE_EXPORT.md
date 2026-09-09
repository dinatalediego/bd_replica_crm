# Stock disponible → Excel ejecutivo

Este módulo convierte a **Medallio DW** en la única fuente de verdad para el reporte de stock disponible y deja Excel únicamente como capa de presentación.

## Flujo

```text
raw_cygnus / raw_mercado
        ↓
core.v_unidades_fuentes
        ↓
analytics.stock_discount_rules
        ↓
analytics.v_stock_disponible_export
        ↓
src/replica_cygnus/stock_export
        ↓
output/stock_disponible/Stock_Disponible_YYYY_MM_DD.xlsx
```

## Regla inicial post-feria

| Proyecto | Descuento |
|---|---:|
| Fénix | 10% |
| Urbanzen | 10% |
| Tizón y Bueno | 10% |

La regla vive en `analytics.stock_discount_rules`; no está pintada dentro del Excel. Para agregar otro proyecto, insertar/actualizar una fila en esa tabla y regenerar el reporte.

## Qué exporta

Solo unidades con `estado_comercial = Disponible` y tipos:

- Departamento
- Estacionamiento
- Depósito

El Excel contiene:

- `00_RESUMEN`: conteo por tipo, stock total, valor lista y valor con descuento.
- una hoja por proyecto: tipo, unidad, tipología, piso, área, precio lista, descuento y precio con descuento.
- sello automático `Actualizado al dd/mm/yyyy – HH:MM`.

## Primera ejecución

Desde la raíz del repositorio:

```bat
pip install -r requirements.txt
scripts\50_exportar_stock_disponible.bat
```

El `.bat` instala/actualiza la vista y luego genera el Excel.

## Ejecución desde Python

Set post-feria por defecto:

```bat
python scripts\stock_export.py --install-view
```

Todos los proyectos configurados:

```bat
python scripts\stock_export.py --install-view --all
```

Proyectos específicos:

```bat
python scripts\stock_export.py --projects "Fénix" "Urbanzen"
```

## Control de calidad recomendado

Antes de enviar el archivo:

```sql
SELECT proyecto, tipo_unidad, count(*) AS unidades,
       sum(precio_lista) AS valor_lista,
       sum(precio_con_descuento) AS valor_con_descuento,
       max(fecha_actualizacion_dato) AS dato_mas_reciente
FROM analytics.v_stock_disponible_export
GROUP BY 1,2
ORDER BY 1,2;
```

Si una unidad aparece sin `precio_lista`, corregir el dato en la capa fuente/canónica; no completar el precio manualmente en Excel.
