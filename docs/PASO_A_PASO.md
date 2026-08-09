# Paso a paso — Windows, DBeaver y PostgreSQL local

## 0. Resultado esperado

Al terminar tendrás:

```text
Redshift de Cygnus
      ↓ cada hora
Python incremental
      ↓
PostgreSQL local: medallio_dw
      ├─ raw_cygnus
      ├─ staging
      ├─ analytics
      └─ etl_control
```

DBeaver podrá conectarse tanto a Redshift como a PostgreSQL local. Power BI podrá consultar PostgreSQL local sin enviar repetidamente consultas largas a Redshift.

---

## 1. Confirma autorización y alcance

Antes de copiar datos, confirma que Cygnus autoriza almacenar la información en tu laptop. Define qué esquemas y columnas puedes conservar. Usa idealmente un usuario de Redshift con permisos únicamente de lectura.

---

## 2. Instala PostgreSQL local

Instala PostgreSQL para Windows. Durante la instalación:

- conserva el puerto `5432`, salvo que ya esté ocupado;
- recuerda la contraseña del usuario `postgres`;
- instala las herramientas de línea de comandos si aparecen como opción;
- no necesitas exponer PostgreSQL a internet.

### Crear la base desde DBeaver

1. Abre DBeaver.
2. Crea una conexión PostgreSQL a:
   - host: `localhost`;
   - puerto: `5432`;
   - base inicial: `postgres`;
   - usuario: `postgres`.
3. Abre un editor SQL con autocommit activado.
4. Ejecuta:

```sql
CREATE DATABASE medallio_dw
    WITH ENCODING = 'UTF8';
```

5. Crea otra conexión DBeaver apuntando a `medallio_dw`.

---

## 3. Descomprime el proyecto

Descomprime el ZIP en una ruta estable, por ejemplo:

```text
C:\Data\replica_redshift_local
```

No lo dejes en Descargas si luego moverás la carpeta, porque la tarea programada guardará la ruta absoluta.

---

## 4. Instala el entorno Python

Haz doble clic en:

```text
scripts\01_instalar.bat
```

El script:

- crea `.venv`;
- instala las dependencias;
- instala el proyecto en modo editable;
- copia `.env.example` como `.env`;
- copia `config\tables.example.yml` como `config\tables.yml`.

Si Python 3.11 no está disponible, intentará usar otra versión de Python 3 instalada.

---

## 5. Configura las credenciales

Abre `.env` con VS Code y reemplaza los valores.

### Redshift

Usa los mismos datos funcionales de tu conexión DBeaver:

```dotenv
REDSHIFT_HOST=...
REDSHIFT_PORT=5439
REDSHIFT_DATABASE=...
REDSHIFT_USER=...
REDSHIFT_PASSWORD=...
REDSHIFT_SSL=true
REDSHIFT_SSLMODE=verify-ca
```

### PostgreSQL local

```dotenv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=medallio_dw
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_SSLMODE=prefer
```

Normalmente no necesitas comillas. Si la contraseña contiene `#`, espacios al inicio/final u otros caracteres interpretables por `.env`, colócala entre comillas dobles.

---

## 6. Prueba las conexiones

Ejecuta:

```text
scripts\02_probar_conexiones.bat
```

Debe mostrar dos líneas:

```text
Redshift OK
PostgreSQL OK
```

Si Redshift falla, revisa VPN, red corporativa, host, puerto, usuario, contraseña y SSL.

---

## 7. Inicializa PostgreSQL

Ejecuta:

```text
scripts\03_inicializar_postgres.bat
```

Se crearán:

- `raw_cygnus`;
- `staging`;
- `analytics`;
- `etl_control.sync_state`;
- `etl_control.sync_runs`.

También puedes ejecutar manualmente `sql\init_local.sql` en DBeaver.

---

## 8. Descubre las tablas reales de Redshift

Ejecuta:

```text
scripts\04_descubrir_tablas.bat
```

El sistema consulta `information_schema` y genera:

```text
reports\source_catalog_AAAAMMDD_HHMMSS.csv
config\tables.generated.yml
```

El CSV contiene:

- esquema y tabla;
- columnas y tipos;
- filas estimadas cuando Redshift las expone;
- candidato de llave;
- candidato de watermark;
- estrategia sugerida.

Las propuestas automáticas son hipótesis. Todas quedan con `enabled: false`.

---

## 9. Define correctamente la llave y el watermark

### Llave

Debe identificar una entidad de forma estable. Ejemplo de validación en Redshift:

```sql
SELECT id, COUNT(*) AS n
FROM grupocygnus.clientes_proyectos
GROUP BY id
HAVING COUNT(*) > 1
LIMIT 20;
```

Si devuelve filas, `id` no es una llave única suficiente.

También comprueba nulos:

```sql
SELECT COUNT(*)
FROM grupocygnus.clientes_proyectos
WHERE id IS NULL;
```

### Watermark

La mejor columna es una fecha de actualización real, como:

```text
updated_at
fecha_actualizacion
fecha_modificacion
```

`fecha_asignacion` solo sirve si cambia o se registra de forma fiable cuando la fila debe volver a copiarse. Si una fila antigua puede editarse sin modificar el watermark, el cambio no será detectado.

Comprueba el rango:

```sql
SELECT
    MIN(fecha_actualizacion),
    MAX(fecha_actualizacion),
    COUNT(*)
FROM grupocygnus.clientes_proyectos;
```

---

## 10. Configura una sola tabla

Edita `config\tables.yml` y deja inicialmente una tabla:

```yaml
version: 1

defaults:
  target_schema: raw_cygnus
  batch_size: 5000
  lookback_hours: 48
  enabled: false
  create_target_if_missing: true
  add_etl_columns: true

tables:
  - source_schema: grupocygnus
    source_table: clientes_proyectos
    target_table: clientes_proyectos
    key_columns: [ID_REAL_CONFIRMADO]
    watermark_column: COLUMNA_REAL_CONFIRMADA
    strategy: incremental
    lookback_hours: 48
    enabled: false
```

Mantén `enabled: false` durante la prueba; el script de prueba usa `--include-disabled` de forma explícita.

---

## 11. Haz un dry run

Desde una terminal abierta en la carpeta raíz:

```bat
.venv\Scripts\python.exe -m replica_cygnus.cli sync ^
  --only clientes_proyectos ^
  --include-disabled ^
  --max-rows 500 ^
  --dry-run
```

Esto muestra el SQL y los parámetros sin copiar filas ni crear la tabla de destino.

---

## 12. Valida la configuración

```bat
.venv\Scripts\python.exe -m replica_cygnus.cli validate ^
  --only clientes_proyectos ^
  --include-disabled
```

Para buscar también duplicados de llave:

```bat
.venv\Scripts\python.exe -m replica_cygnus.cli validate ^
  --only clientes_proyectos ^
  --include-disabled ^
  --deep
```

La validación profunda puede consumir más tiempo en tablas grandes.

---

## 13. Prueba 500 filas

Ejecuta:

```text
scripts\05_probar_una_tabla.bat clientes_proyectos
```

Luego valida en DBeaver:

```sql
SELECT COUNT(*)
FROM raw_cygnus.clientes_proyectos;
```

```sql
SELECT *
FROM etl_control.sync_runs
ORDER BY started_at DESC
LIMIT 10;
```

```sql
SELECT *
FROM etl_control.sync_state
WHERE source_table = 'clientes_proyectos';
```

---

## 14. Ejecuta la carga completa inicial

Cuando la prueba sea correcta, ejecuta sin `--max-rows`:

```bat
.venv\Scripts\python.exe -m replica_cygnus.cli sync ^
  --only clientes_proyectos ^
  --include-disabled
```

Para una tabla grande, realiza esta primera carga cuando Redshift tenga menor demanda. El sistema procesa por lotes, pero la consulta inicial puede recorrer un volumen considerable.

---

## 15. Activa la tabla

En `config\tables.yml` cambia:

```yaml
enabled: true
```

Agrega y valida las demás tablas una por una. No habilites todas antes de confirmar sus llaves y watermarks.

---

## 16. Ejecuta todas las tablas habilitadas

```text
scripts\06_sincronizar_habilitadas.bat
```

El comando equivalente es:

```bat
.venv\Scripts\python.exe -m replica_cygnus.cli sync
```

---

## 17. Programa la ejecución cada hora

Ejecuta:

```text
scripts\07_crear_tarea_horaria.bat
```

Se creará una tarea llamada:

```text
Medallio - Replica Redshift Local
```

Características:

- se repite cada hora;
- ignora una nueva ejecución si la anterior continúa;
- intenta ejecutarse cuando Windows vuelve a estar disponible;
- corta una ejecución que supere 55 minutos;
- mantiene la repetición configurada durante 10 años.

La laptop debe estar encendida y tener acceso a Redshift. Si está apagada, no existe una máquina que ejecute el proceso. La tarea se registra para el usuario actual; para ejecutarla con la sesión cerrada, abre el Programador de tareas, entra a sus propiedades y selecciona “Ejecutar tanto si el usuario inició sesión como si no”, ingresando la contraseña de Windows cuando se solicite.

Para eliminar la automatización:

```text
scripts\08_eliminar_tarea_horaria.bat
```

---

## 18. Revisa estado y errores

Ejecuta:

```text
scripts\09_ver_estado.bat
```

Revisa también:

```text
logs\replica.log
logs\replica.log.1
...
```

Consulta de fallos:

```sql
SELECT
    started_at,
    source_schema,
    source_table,
    status,
    rows_extracted,
    rows_loaded,
    error_message
FROM etl_control.sync_runs
WHERE status = 'FAILED'
ORDER BY started_at DESC;
```

---

## 19. Conecta Power BI

En Power BI Desktop:

1. Obtener datos.
2. PostgreSQL database.
3. Servidor: `localhost:5432`.
4. Base: `medallio_dw`.
5. Selecciona tablas de `analytics` cuando las construyas; usa `raw_cygnus` solo como capa de origen.

La arquitectura recomendada es:

```text
raw_cygnus → staging → analytics → Power BI
```

No construyas toda la lógica final directamente sobre tablas raw.

---

## 20. Qué ocurre en cada ejecución incremental

1. Lee el último watermark exitoso.
2. Resta la ventana de superposición, por ejemplo 48 horas.
3. Consulta únicamente ese rango en Redshift.
4. Descarga filas por lotes.
5. Inserta el lote en una tabla temporal PostgreSQL.
6. Deduplica por llave, priorizando el watermark más reciente.
7. Ejecuta `INSERT ... ON CONFLICT DO UPDATE`.
8. Guarda el nuevo watermark.
9. Registra filas, estado y error del run.

La superposición hace que algunas filas se lean nuevamente, pero el `UPSERT` evita duplicarlas.

---

## 21. Limitaciones conocidas

### Eliminaciones

Una réplica incremental basada en watermark no sabe que una fila fue borrada físicamente del origen. Soluciones futuras:

- indicador lógico `deleted_at` o `estado`;
- reconciliación nocturna de llaves;
- recarga completa de tablas pequeñas;
- CDC administrado por la plataforma fuente.

### Laptop apagada

El proceso no se ejecuta cuando la laptop está apagada. Para continuidad 24/7 habría que migrar el mismo código a una VM, contenedor o servicio cloud.

### Cambios de tipo

El sistema agrega columnas nuevas, pero no cambia o elimina automáticamente columnas existentes. Los cambios de tipo deben revisarse para evitar pérdida de datos.

### Watermark incorrecto

Si la columna configurada no cambia cuando se actualiza una fila, esa modificación puede no llegar a PostgreSQL. La selección del watermark es la decisión técnica más importante.

---

## 22. Pruebas del proyecto

```bat
.venv\Scripts\python.exe -m pytest
```

Las pruebas incluidas cubren:

- validación de identificadores;
- mapeo de tipos Redshift → PostgreSQL;
- construcción de consultas sin `SELECT *`;
- ventana de superposición;
- reglas mínimas de configuración.

---

# Extensión v0.2.0 — Decision Intelligence

Después de completar la réplica y ejecutar `scripts\03_inicializar_postgres.bat`, DBeaver mostrará también:

```text
features
decision_intelligence
model_control
experiments
```

Valida los contratos:

```powershell
.\scripts\10_validar_contratos_decision.bat
```

Luego ejecuta una demo completamente sintética:

```powershell
.\scripts\11_demo_decisiones.bat
```

Abre `reports\decision_demo.csv`. La lógica demostrada es:

```text
probabilidad + CATE/uplift
→ valor incremental esperado
→ restricción de capacidad
→ acción recomendada
```

No conectes todavía esta demo a decisiones reales. Primero construye un dataset histórico `as-of`, valida temporalmente el modelo, define la utilidad económica con el negocio y diseña cómo identificar el efecto causal de la intervención.
