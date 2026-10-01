# Diagnóstico y corrección de TimeoutError en Redshift

## Síntoma

El traceback termina en `ssl.py -> read -> TimeoutError: The read operation timed out`, incluso al consultar metadatos de una tabla.

## Causa probable en v0.2.1

La variable histórica `REDSHIFT_CONNECT_TIMEOUT=20` se pasaba al argumento `timeout` de `redshift_connector`. Ese argumento aplica al socket del driver, de modo que 20 segundos puede ser demasiado agresivo bajo WLM, carga del cluster, VPN o latencia de red.

## Cambio v0.2.2

- `REDSHIFT_SOCKET_TIMEOUT=300` por defecto.
- TCP keepalive habilitado.
- `SHOW COLUMNS` se usa primero para obtener metadatos.
- fallback a `SVV_COLUMNS`.
- nuevo diagnóstico `scripts\12_diagnosticar_redshift.bat`.

## .env recomendado

```dotenv
REDSHIFT_SOCKET_TIMEOUT=300
REDSHIFT_TCP_KEEPALIVE=true
REDSHIFT_TCP_KEEPALIVE_IDLE=30
REDSHIFT_TCP_KEEPALIVE_INTERVAL=15
REDSHIFT_TCP_KEEPALIVE_COUNT=5
REDSHIFT_STATEMENT_TIMEOUT_MS=900000
```

`REDSHIFT_CONNECT_TIMEOUT` queda obsoleto para Redshift en esta versión.

## Prueba

```powershell
.\scripts\12_diagnosticar_redshift.bat grupocygnus proforma_unidad
```

Luego:

```powershell
.\.venv\Scripts\python.exe -m replica_cygnus.cli validate --only proforma_unidad --include-disabled --deep
.\scripts\05_probar_una_tabla.bat proforma_unidad
```


## Recuperación automática del refresh maestro

Desde septiembre de 2026, el `sync` usado por `scripts\run_hourly.bat` abre una conexión Redshift independiente por tabla e intento.

Esto evita el patrón observado donde un timeout en `unidades` dejaba el socket inválido y hacía que `proyectos` y `datos_extras` fallaran inmediatamente al intentar leer metadatos con la misma conexión.

Valores por defecto:

```dotenv
REDSHIFT_SYNC_MAX_ATTEMPTS=2
REDSHIFT_SYNC_RETRY_SECONDS=5
```

Ante errores transitorios de red/timeout:

1. se registra el fallo de ese intento;
2. se cierra la conexión Redshift;
3. se abre una conexión nueva;
4. se reintenta la misma tabla;
5. las tablas siguientes siempre comienzan con una conexión limpia.

La carga incremental sigue siendo idempotente: si un intento alcanzó a cargar lotes antes del timeout, el reintento vuelve a procesar la ventana sin duplicar la llave, porque la réplica usa UPSERT y el watermark solo avanza al completar correctamente el run.

Si una tabla sigue fallando después del último intento, el RAW termina con código de error y el refresh maestro **no promueve CORE/analytics sobre un snapshot incompleto**. Observabilidad sí se ejecuta para dejar evidencia del fallo.

Los fallbacks de metadatos `SHOW COLUMNS -> SVV_COLUMNS -> information_schema.columns` se conservan para errores funcionales/no transitorios. Si el error es un timeout de socket, se abandona el fallback sobre esa conexión porque el driver ya no puede reutilizarla de forma fiable.
