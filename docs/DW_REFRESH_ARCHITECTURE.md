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
03 CORE commercial refresh
   ↓
04 analytics.unidades_powerbi
   ↓
05 Absorption Phase B incremental + QA
   ↓
06 CORE lifecycle contract
   ↓
07 pricing projection mart + QA
   ↓
08 materialized views de core / analytics / analytics_compare / gold
   ↓
99 observability
```

Las `VIEW` normales de PostgreSQL no almacenan datos y, por tanto, no requieren un refresh de filas. El schema sync asegura que su **definición** esté alineada con el código del repositorio. Las `MATERIALIZED VIEW` sí almacenan resultados; por eso se descubren y refrescan automáticamente en las capas de serving.

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

- Todas las tablas Redshift declaradas en `config/tables.yml` con `enabled: true`.
- `grupocygnus.archivos` mediante `config/hourly_required_tables.yml`, usando `full_refresh` para no colapsar varios archivos de una misma `codigo_proforma`.
- `staging.clientes_calidad`, como contrato DQ derivado de `raw_cygnus.clientes`, incluyendo limpieza de DNI/contacto, prioridad `celulares -> telefono`, clasificación de números extranjeros, flags `dq_*` y score de calidad.
- `analytics.archivos_procesos`, como vista derivada de `raw_cygnus.archivos` con `papel_blanco`, `contrato_con_papel_blanco`, `tiene_pasos_en_blanco`, `Rank`, `ranking_contrato` y `ranking_pasos`.
- Las dimensiones CORE.
- `analytics.unidades_powerbi`.
- El ciclo comercial y absorción incremental.
- El simulador de pricing `analytics.fact_proyeccion_pricing` y su QA.
- Las definiciones registradas de `core`, `analytics`, `analytics_compare`, `pricing` y observabilidad.
- Todas las materialized views existentes en `core`, `analytics`, `analytics_compare` y `gold`.
- La observabilidad del ciclo, incluso si un paso anterior falla.

## Límites intencionales

Una tabla nueva de Redshift no se incorpora automáticamente si nunca fue declarada en `config/tables.yml`: todavía se requieren llave, watermark y estrategia verificadas. Esta barrera evita copiar tablas desconocidas con una granularidad incorrecta.

`archivos` es una excepción versionada y explícita porque una `codigo_proforma` puede tener múltiples archivos. Por eso no se usa la llave sugerida automáticamente `[codigo_proforma]` para un UPSERT incremental: el refresh horario usa reemplazo completo y preserva todas las filas antes de construir `analytics.archivos_procesos`.

`raw_mercado` tampoco inventa una fuente nueva por sí solo: cuando cambie el CSV/Excel de mercado debe cargarse mediante su loader. Una vez cargado, las vistas multifuente se mantienen dentro del refresh maestro.

El schema `gold` se incluye para refrescar materialized views existentes, pero actualmente el repositorio no contiene definiciones SQL versionadas de una capa Gold general. Cuando se incorporen, deben registrarse como un componente de `schema_sync.py` para que también queden gobernadas por checksum.
