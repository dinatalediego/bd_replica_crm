# Loader de raw_mercado

Carga controlada de un CSV externo a PostgreSQL `raw_mercado.unidades`.

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
5. Crea `raw_mercado.unidades` si todavía no existe y agrega columnas nuevas de forma no destructiva.
6. Antes de reemplazar datos crea un snapshot físico con nombre `raw_mercado.unidades_snapshot_YYYYMMDD_HHMMSS_RUNID`.
7. Por defecto hace refresh completo (`TRUNCATE` + carga) dentro de la misma transacción.
8. Agrega `_source_file`, `_source_sha256` y `_loaded_at` para lineage.
9. Ejecuta QA de conteo de filas.
10. Marca la ejecución como `success` o `failed`.

Si cualquier paso falla antes del commit, PostgreSQL revierte la modificación del target.

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
