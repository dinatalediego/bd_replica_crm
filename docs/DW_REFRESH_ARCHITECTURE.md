# Medallio DW — refresh maestro autoconsistente

## Objetivo

El mantenimiento operativo del data warehouse y de los datasets que consumen los dashboards de Power BI se reduce a un único comando:

```powershell
.\scripts\run_hourly.bat
```

La tarea de Windows `Medallio - Replica Redshift Local` puede seguir apuntando al mismo BAT. No es necesario recrearla cuando el repositorio cambia, siempre que la ruta del proyecto siga siendo la misma.

## Flujo

```text
Redshift
   ↓
01 RAW sync de todas las tablas enabled=true en config/tables.yml
   ↓
01b RAW obligatorio: grupocygnus.archivos -> raw_cygnus.archivos
   ↓
02 schema sync por checksum
   ├─ staging.clientes_calidad
   ├─ analytics.archivos_procesos
   ├─ CORE commercial
   ├─ Absorption Phase B
   ├─ CORE lifecycle
   ├─ analytics.unidades_powerbi
   ├─ unidades multifuente / analytics_compare
   └─ observability
   ↓
02b staging.clientes_calidad refresh + health gate
   ↓
02c marketing audiences refresh
   ↓
02d portal conversion attribution (ORIGEN > MEDIO_ACTUAL, conversion única por persona)
   ↓
03 CORE commercial refresh
   ↓
04 analytics.unidades_powerbi
   ↓
05 Absorption Phase B incremental + QA
   ↓
06 CORE lifecycle contract
   ↓
06b evolución comercial diaria
    └─ analytics.comercial_unidad_mes / analytics.comercial_proyecto_mes
   ↓
07 pricing projection mart + QA
   ↓
07b datasets econométricos (máximo una corrida exitosa al día)
   ↓
08 materialized views de core / analytics / analytics_compare / gold
   ↓
99 observability
```

Las `VIEW` normales de PostgreSQL no almacenan datos y, por tanto, no requieren un refresh de filas. El schema sync asegura que su **definición** esté alineada con el código del repositorio. Las `MATERIALIZED VIEW` sí almacenan resultados; por eso se descubren y refrescan automáticamente en las capas de serving.

`analytics.comercial_proyecto_mes` y `analytics.comercial_unidad_mes` sí son tablas físicas derivadas. Desde la integración del Readiness Gate de la Sala de decisiones, el refresh maestro ejecuta `scripts/refresh_evolucion_comercial.py --once-per-day` después de Absorption Phase B. Si ya existe un corte uniforme de hoy en Lima, el paso devuelve `SKIP_ALREADY_TODAY`; si no, reconstruye ambos marts. De este modo ya no dependen indirectamente de que la corrida econométrica sea la que los refresque.

## SLA mínimo de refresco

La tarea de Windows despierta cada hora. Para las fuentes Redshift **declaradas y habilitadas** en `config/tables.yml`, el Source Gate usa el ledger `etl_control.sync_state`: por defecto los incrementales vencen a las 4 horas y los `full_refresh` a las 24 horas. Esto implica un objetivo operativo de al menos una actualización diaria para toda fuente habilitada, siempre que el PC, la tarea y Redshift estén disponibles.

La garantía no se extiende a tablas Redshift nunca declaradas o con `enabled: false`: Medallio no inventa llaves ni watermarks para copiar fuentes desconocidas. Una tabla nueva debe incorporarse explícitamente al contrato de réplica.

El Programador de tareas conserva un único entrypoint (`scripts/run_hourly.bat`). El instalador usa `MultipleInstances=IgnoreNew` y un límite de 90 minutos por corrida para dar margen al refresh diario de marts sin crear solapamientos.

## Readiness de la Sala de decisiones

El exportador `scripts/export_decision_room.py` añade un gate por proyecto. Un proyecto queda `READY` solo cuando pasan simultáneamente estas cuatro reglas:

1. `freshness`: el `source_cutoff` del mart corresponde al día actual de Lima.
2. `stock_reconciliation`: el `stock_close` histórico en el origen coincide con el stock implícito del forecast (`stock_remaining + prediction`).
3. `quality`: no hay `review_units` pendientes en el histórico entregado.
4. `forecast_availability`: están disponibles exactamente los horizontes 1–6 del run seleccionado.

Si alguna regla falla el proyecto sigue presente en el JSON, pero queda `BLOCKED` con un código explícito (`STALE_SOURCE`, `STOCK_MISMATCH`, `DATA_QUALITY_QUARANTINE` o `FORECAST_INCOMPLETE`). Así la interfaz puede mostrar el dato sin presentarlo como apto para decisión.

## Schema migrations autoconsistentes

`scripts/schema_sync.py` calcula un SHA-256 por componente SQL y lo registra en:

```text
etl_control.schema_migrations
```

En cada ejecución:

1. Si el código SQL no cambió y los objetos esperados existen, no hace trabajo innecesario.
2. Si cambió el SQL después de un `git pull`, reaplica solamente ese componente.
3. Si el checksum coincide pero falta una tabla, vista o procedimiento esperado, detecta drift y lo reinstala.
4. Si una migración falla, registra `FAILED` y detiene el refresh antes de construir capas dependientes.

Esto evita el problema de tener un `run_incremental.py` nuevo llamando a un procedimiento que todavía no fue instalado en PostgreSQL.

## Comandos útiles

Refresh completo manual:

```powershell
.\scripts\run_hourly.bat
```

Forzar solo el mart comercial aunque ya haya corrido hoy:

```powershell
.\.venv\Scripts\python.exe .\scripts\refresh_evolucion_comercial.py
```

Ejecutarlo con la misma protección diaria del orquestador:

```powershell
.\.venv\Scripts\python.exe .\scripts\refresh_evolucion_comercial.py --once-per-day
```

Ver estado de componentes SQL sin modificarlos:

```powershell
.\.venv\Scripts\python.exe .\scripts\schema_sync.py --status
```

Forzar reinstalación de definiciones SQL registradas:

```powershell
.\.venv\Scripts\python.exe .\scripts\schema_sync.py --force
```

Reinstalar únicamente Phase B:

```powershell
.\.venv\Scripts\python.exe .\scripts\schema_sync.py --only absorption_phase_b --force
```

## Qué se actualiza automáticamente

- Todas las tablas Redshift declaradas en `config/tables.yml` con `enabled: true` y vencidas según su Source Gate.
- `grupocygnus.archivos` mediante `config/hourly_required_tables.yml`, usando `full_refresh` para no colapsar varios archivos de una misma `codigo_proforma`.
- `staging.clientes_calidad`, como contrato DQ derivado de `raw_cygnus.clientes`, incluyendo limpieza de DNI/contacto, prioridad `celulares -> telefono`, clasificación de números extranjeros, flags `dq_*` y score de calidad.
- Audiencias de marketing y atribución portal.
- `analytics.archivos_procesos`, como vista derivada de `raw_cygnus.archivos`.
- Las dimensiones CORE.
- `analytics.unidades_powerbi`.
- El ciclo comercial y absorción incremental.
- `analytics.comercial_unidad_mes` y `analytics.comercial_proyecto_mes` al menos una vez por día de Lima.
- El simulador de pricing `analytics.fact_proyeccion_pricing` y su QA.
- Los datasets econométricos con su propio gate diario.
- Las definiciones registradas de `core`, `analytics`, `analytics_compare`, `pricing` y observabilidad.
- Todas las materialized views existentes en `core`, `analytics`, `analytics_compare` y `gold`.
- La observabilidad del ciclo, incluso si un paso anterior falla.

## Límites intencionales

Una tabla nueva de Redshift no se incorpora automáticamente si nunca fue declarada en `config/tables.yml`: todavía se requieren llave, watermark y estrategia verificadas. Esta barrera evita copiar tablas desconocidas con una granularidad incorrecta.

`archivos` es una excepción versionada y explícita porque una `codigo_proforma` puede tener múltiples archivos. Por eso no se usa la llave sugerida automáticamente `[codigo_proforma]` para un UPSERT incremental: el refresh horario usa reemplazo completo y preserva todas las filas antes de construir `analytics.archivos_procesos`.

`raw_mercado` tampoco inventa una fuente nueva por sí solo: cuando cambie el CSV/Excel de mercado debe cargarse mediante su loader. Una vez cargado, las vistas multifuente se mantienen dentro del refresh maestro.

El schema `gold` se incluye para refrescar materialized views existentes, pero actualmente el repositorio no contiene definiciones SQL versionadas de una capa Gold general. Cuando se incorporen, deben registrarse como un componente de `schema_sync.py` para que también queden gobernadas por checksum.
