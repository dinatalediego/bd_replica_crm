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
