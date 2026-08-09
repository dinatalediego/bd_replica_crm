# Arquitectura del sistema

```text
Amazon Redshift (solo lectura)
        |
        | SQL con lista explícita de columnas
        | filtro incremental por watermark
        v
Python / redshift-connector
        |
        | lotes configurables, por defecto 5 000 filas
        v
Tabla temporal PostgreSQL
        |
        | UPSERT por llave o reemplazo completo controlado
        v
PostgreSQL local
  ├─ raw_cygnus      copia operacional
  ├─ staging         transformaciones intermedias futuras
  ├─ analytics       data marts para Power BI / ML
  └─ etl_control     estado, auditoría y ejecuciones
```

## Principios incorporados

- **Solo lectura en Redshift:** el sistema únicamente ejecuta `SELECT` e introspección.
- **Sin `SELECT *`:** consulta una lista explícita de columnas obtenida del catálogo.
- **Carga por lotes:** evita guardar toda la tabla en la memoria de la laptop.
- **Idempotencia:** la estrategia incremental usa `UPSERT` y una ventana de superposición.
- **Auditoría:** cada ejecución queda registrada en `etl_control.sync_runs`.
- **Marca de agua:** el último valor exitoso queda en `etl_control.sync_state`.
- **Bloqueo:** PostgreSQL impide dos ejecuciones simultáneas de la misma tabla.
- **Evolución de esquema aditiva:** las columnas nuevas se agregan; no se borran columnas automáticamente.
- **Seguridad:** las credenciales viven en `.env`, excluido de Git.

## Estrategias

### incremental

Adecuada para tablas transaccionales. Requiere:

- `key_columns`: llave estable para el `UPSERT`.
- `watermark_column`: fecha/hora o secuencia que cambie cuando se modifica una fila.
- `lookback_hours`: superposición para recoger cambios tardíos.

### full_refresh

Adecuada para catálogos pequeños. Primero carga todo en una tabla temporal; solo al finalizar reemplaza el destino. Si la extracción falla, la tabla local anterior no se trunca.

### append

Adecuada únicamente para eventos inmutables con watermark. No puede corregir filas existentes ni deduplicar sin una llave. Para la mayoría de tablas de Cygnus es preferible `incremental`.

## Alcances que no incluye la versión 0.1

- Propagación automática de eliminaciones físicas realizadas en Redshift.
- CDC nativo o streaming en tiempo real.
- Migraciones destructivas de tipos o columnas.
- UNLOAD a S3 para cargas iniciales extremadamente grandes.
- Alertas por correo o Teams.

Estas capacidades pueden añadirse después de estabilizar las primeras tablas.
