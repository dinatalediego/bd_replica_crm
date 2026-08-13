# Paso a paso — Fase B

## Paso 0 — Pausar la tarea horaria

En PowerShell:

```powershell
Disable-ScheduledTask -TaskName "Medallio - Replica Redshift Local"
```

Si no tienes permiso, abre Programador de tareas y deshabilítala temporalmente.

## Paso 1 — Actualizar `tables.yml`

Ejecutar desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe .\src\absorption_phase_b\patch_tables_yml.py
```

El script:

- hace backup de `config\tables.yml`;
- localiza `source_table: procesos`;
- cambia solamente esa entrada a:

```yaml
key_columns: [nombre, id]
```

## Paso 2 — Validar source key

Ejecutar en DBeaver:

`sql/11_raw_repair/00_validate_source_key.sql`

Deben cumplirse:

- `(nombre,id)` duplicados = 0 en PostgreSQL actual;
- `id` global no debe usarse como unique key.

## Paso 3 — Reparar `raw_cygnus.procesos`

Ejecutar:

```powershell
.\scripts\22_repair_procesos_source_key.bat
```

Este proceso:

1. lee `grupocygnus.procesos` completo desde Redshift;
2. valida unicidad de `(nombre,id)`;
3. crea backup local de la tabla actual;
4. elimina restricciones UNIQUE/PK exclusivamente sobre `id`;
5. reemplaza transaccionalmente el contenido local;
6. crea unique index `(nombre,id)`;
7. valida:
   - 5,031 filas (o el total actual del origen);
   - mismo número de `(nombre,id)` distintos.

No modifica Redshift.

## Paso 4 — Reconciliar

En Redshift:

```sql
SELECT
    COUNT(*) filas,
    COUNT(*) - COUNT(DISTINCT (nombre || '|' || CAST(id AS VARCHAR))) AS duplicados_composite
FROM grupocygnus.procesos;
```

En PostgreSQL:

```sql
SELECT
    COUNT(*) filas,
    COUNT(*) - COUNT(DISTINCT (nombre, id)) AS duplicados_composite
FROM raw_cygnus.procesos;
```

Los conteos deben coincidir.

## Paso 5 — Instalar DDL de Fase B

```powershell
.\scripts\23_instalar_absorption_phase_b.bat
```

Crea tablas, funciones y procedimientos.
No toca RAW.

## Paso 6 — Backfill Fase B

```powershell
.\scripts\24_backfill_absorption_phase_b.bat
```

Ejecuta en PostgreSQL:

`CALL analytics.refresh_absorption_phase_b_full();`

## Paso 7 — QA

```powershell
.\scripts\25_qa_absorption_phase_b.bat
```

O en DBeaver:

```sql
SELECT *
FROM observability.absorption_quality_results
ORDER BY checked_at DESC, check_name;
```

## Paso 8 — Ver resultados

```sql
SELECT * FROM analytics.int_unidad_entrada_stock LIMIT 20;
SELECT * FROM analytics.int_proforma_minuta LIMIT 20;
SELECT * FROM analytics.int_ciclo_comercial_unidad LIMIT 20;
SELECT * FROM analytics.fact_movimientos_stock LIMIT 50;
```

## Paso 9 — Reactivar tarea

Cuando la réplica y Fase B estén correctas:

```powershell
Enable-ScheduledTask -TaskName "Medallio - Replica Redshift Local"
```

La integración automática de Fase B al job horario se hace después de validar el primer backfill.

## OPEN BUSINESS RULE que permanece

La propagación de `fecha_de_minuta` a estacionamientos/depósitos NO se implementa todavía.
`int_proforma_minuta` conserva la regla histórica residencial:

- `Separacion`
- `estado = 'Activo'`
- `tipo_unidad_principal` en departamento flat/duplex
