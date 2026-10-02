# Loader de raw_mercado

Carga controlada de un CSV externo a PostgreSQL `raw_mercado.unidades`.

Si `nombre` viene vacío, el loader lo completa con el tipo de unidad y el
número del último segmento de `codigo`: `AMMA-T1-X02-25-2502` produce
`Departamento 2502`. Si el código no termina en un segmento numérico, usa el
código completo. Un `nombre` informado en el CSV se conserva. La carga se
detiene si los nombres finales se repiten, porque Power BI usa esa columna
como clave. El CSV de origen permanece intacto.

## Comando cotidiano (Windows)

Desde la raíz del repositorio:

```powershell
.\scripts\07_cargar_raw_mercado.bat "C:\ruta\nuevo_mercado.csv"
```

O directamente con Python:

```powershell
python .\scripts\load_raw_mercado.py "C:\ruta\nuevo_mercado.csv"
```

El loader usa `DATABASE_URL`; como fallback acepta `POSTGRES_URL`.

## Ciclo de carga

1. Valida existencia, extensión y cabecera del CSV.
2. Normaliza nombres de columnas.
3. Calcula SHA-256 del archivo para trazabilidad.
4. Registra la ejecución en `etl_control.raw_mercado_load_runs`.
5. Exige la tabla canónica `raw_mercado.unidades` con `nombre` y las demás columnas obligatorias.
6. Antes de reemplazar datos crea un snapshot físico con nombre `raw_mercado.unidades_snapshot_YYYYMMDD_HHMMSS_RUNID`.
7. Por defecto hace refresh completo (`TRUNCATE` + carga) dentro de la misma transacción.
8. Guarda `_etl_source_run_id` en las unidades y el archivo/hash en `etl_control.raw_mercado_load_runs`.
9. Ejecuta QA de conteo de filas.
10. Marca la ejecución como `success` o `failed`.

Si cualquier paso falla antes del commit, PostgreSQL revierte la modificación del target.

## Reparar nombres ya cargados sin volver a leer el CSV ni Redshift

Después de actualizar el repositorio, desde su raíz:

```powershell
.\.venv\Scripts\python.exe .\scripts\unidades_powerbi.py
```

Ese script completa solo los `nombre` vacíos en `raw_mercado.unidades` y
reinstala `analytics.unidades_powerbi`. También forma parte del refresh local
habitual. Informa la cantidad de nombres vacíos y repetidos que queden.

Verificación directa en PostgreSQL:

```sql
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE NULLIF(BTRIM(nombre), '') IS NULL) AS sin_nombre,
       COUNT(DISTINCT LOWER(NULLIF(BTRIM(nombre), ''))) AS nombres_distintos
FROM raw_mercado.unidades;

SELECT codigo, nombre, tipo_unidad
FROM raw_mercado.unidades
ORDER BY codigo
LIMIT 10;
```

Actualiza `unidades_mercado` en Power BI tras verificar los conteos.

## Modos opcionales

Carga sin snapshot (solo para casos deliberados):

```powershell
python .\scripts\load_raw_mercado.py archivo.csv --no-snapshot
```

Append en vez de refresh completo:

```powershell
python .\scripts\load_raw_mercado.py archivo.csv --append
```

## Auditoría

```sql
SELECT *
FROM etl_control.raw_mercado_load_runs
ORDER BY run_id DESC
LIMIT 20;
```

Última carga:

```sql
SELECT nombre_proyecto, COUNT(*) AS unidades
FROM raw_mercado.unidades
GROUP BY nombre_proyecto
ORDER BY nombre_proyecto;
```

## Política recomendada

Para el stock de mercado usar el modo por defecto: snapshot + refresh completo. `--append` debe reservarse para fuentes realmente incrementales.
