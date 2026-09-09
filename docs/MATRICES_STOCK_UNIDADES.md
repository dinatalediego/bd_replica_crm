# Medallio · Matrices Stock & Unidades

Interfaz local en Streamlit para explorar inventario comercial sin crear una nueva fuente de datos.

## Arquitectura

```text
raw_cygnus / raw_mercado
          ↓
core.v_unidades_fuentes
          ↓
 ┌──────────────────────────────┐
 │                              │
analytics.v_stock_disponible_export   rama Unidades (flag_departamento)
 │                              │
Excel + pestaña Stock           matrices visuales (no exporta)
```

## Dos ramas de la interfaz

### 1. Stock disponible

- Lee exactamente `analytics.v_stock_disponible_export`.
- Incluye departamentos, estacionamientos y depósitos disponibles.
- Muestra precio lista, descuento y precio con descuento.
- Permite regenerar y descargar el mismo Excel del módulo `stock_export`.

### 2. Unidades · departamentos

Primera versión limitada a `flag_departamento = true` (nombre canónico singular del flag).

La matriz usa por defecto el mismo layout visual del tablero comercial:

- filas: `piso`;
- columnas: `tipologia_ubicacion`;
- color: estado comercial;
- valor de celda: métrica seleccionada.

También puede invertirse a `piso en columnas` desde la interfaz.

Métricas iniciales:

1. Precio por m² en US$.
2. Precio por m² en S/.
3. Precio de lista (S/ o US$ según selector).
4. Precio con descuento (S/ o US$ según selector).

Para precio/m² la interfaz calcula `precio_lista / area_total`; si no puede hacerlo, usa `precio_m2` de origen como fallback. El tipo de cambio es editable por proyecto.

Defaults actuales de TC usados solo como valor inicial de interfaz:

- Matera / Nápoles: 3.70.
- Torre Marsano: 3.40.
- Resto: 3.80.

## Estados y colores

La agrupación de `estado_comercial` conserva la semántica operativa visual:

- Disponible: amarillo.
- No disponible / bloqueado: gris.
- Proceso de separación / separado: naranja.
- Proceso de venta / vendido / proceso de aprobación: verde.
- Proceso de entrega / entregado: morado.

La matriz no cambia el estado en Medallio; solo lo agrupa para visualización.

## Ejecutar

Después de actualizar la rama e instalar dependencias:

```bat
scripts\51_matrices_stock_unidades.bat
```

El launcher:

1. comprueba Streamlit;
2. valida `core.v_unidades_fuentes` y la capa SQL de stock;
3. abre la aplicación local en `http://localhost:8501`.

Para cerrarla, usar `Ctrl+C` en la terminal donde corre Streamlit.

## Frescura

La interfaz usa caché de 60 segundos. El botón **Actualizar datos** borra la caché y vuelve a consultar `medallio_dw`.

## Alcance deliberado

La rama Unidades es solo visual por ahora. No se genera archivo de unidades hasta validar layout, estados, métricas y reglas de precio/descuento con datos reales.