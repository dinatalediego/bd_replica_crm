# Integración aditiva `raw_mercado`

Este paquete agrega una ingesta independiente de archivos Excel/CSV a PostgreSQL sin modificar la réplica `raw_cygnus`, `run_hourly.bat` ni la tarea programada existente.

## Objetos creados

- `raw_mercado.cargas`: auditoría e idempotencia por hash de archivo.
- `raw_mercado.unidades_historial`: snapshots append-only.
- `raw_mercado.unidades`: último estado conocido por `source_id + codigo_unidad`.
- `raw_mercado.v_unidades_actual`: vista de conveniencia sobre el estado vigente.

Todas las sentencias DDL usan `IF NOT EXISTS`. La instalación no elimina ni reemplaza objetos preexistentes.

## Archivos que deben copiarse al repositorio

```text
config/mercado_sources.yml
requirements-market.txt
scripts/40_instalar_raw_mercado.bat
scripts/41_validar_unidades_mercado.bat
scripts/42_cargar_unidades_mercado.bat
src/mercado_ingestion/
tests/mercado_ingestion/
```

## Instalación

Primero, desde la carpeta descomprimida, copia el overlay sin sobrescribir archivos:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\install_overlay.ps1 `
  -RepositoryRoot C:\Cygnus\projects\medallio_dw
```

El instalador se detiene antes de copiar si encuentra cualquier ruta en conflicto.

Después, desde la raíz de `medallio_dw`:

```powershell
.\scripts\40_instalar_raw_mercado.bat
```

El script instala únicamente el lector de Excel faltante e inicializa el esquema.

## Validación sin escritura

```powershell
.\scripts\41_validar_unidades_mercado.bat `
  "C:\Cygnus\otros_proyectos\unidades_amma_torre_marsano.xlsx" `
  amma_torre_marsano `
  2026-08-20
```

## Primera carga

```powershell
.\scripts\42_cargar_unidades_mercado.bat `
  "C:\Cygnus\otros_proyectos\unidades_amma_torre_marsano.xlsx" `
  amma_torre_marsano `
  2026-08-20
```

La fecha es opcional; si se omite, se usa la fecha local de ejecución en Lima. Para reconstruir historia se recomienda proporcionarla explícitamente.

## Comprobación en DBeaver

```sql
SELECT * FROM raw_mercado.cargas ORDER BY iniciado_en DESC;

SELECT COUNT(*) FROM raw_mercado.unidades_historial;
SELECT COUNT(*) FROM raw_mercado.unidades;

SELECT
    fecha_snapshot,
    COUNT(*) AS unidades
FROM raw_mercado.unidades_historial
GROUP BY fecha_snapshot
ORDER BY fecha_snapshot;
```

## Idempotencia y protección histórica

- El mismo archivo no se carga dos veces para la misma fuente (`source_id + hash_archivo`).
- Cada snapshot impide códigos de unidad duplicados.
- Una carga histórica antigua se agrega al historial, pero no reemplaza un estado actual más reciente.
- Si falla la escritura, la carga se marca `FAILED` y las filas parciales se revierten.
