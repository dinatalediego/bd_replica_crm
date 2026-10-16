# Medallio AI Runtime

## Objetivo

Convertir los motores analíticos y ML ya existentes en `bd_replica_crm` en una operación repetible con mínima intervención manual.

El runtime no reemplaza el refresh maestro del DW. La tarea existente `Medallio - Replica Redshift Local` sigue apuntando a `scripts/run_hourly.bat`. La nueva capa se ejecuta aparte para que un fallo de un modelo no bloquee RAW/CORE/analytics.

## Qué ejecuta

### Hourly

- captura evidencia viva de lead scoring;
- intenta scoring con el CHAMPION vigente;
- sincroniza recomendaciones;
- actualiza outcomes maduros.

Si todavía no existe CHAMPION, el scoring se registra como fallo blando y la captura de evidencia sigue funcionando.

### Daily

- ejecuta `temporal_science.py run --once-per-day`;
- reutiliza el forecasting macro gobernado, que ya tiene idempotencia mensual;
- mide outcomes de forecasting y lead scoring.

### Weekly

- entrena y evalúa un challenger de lead scoring;
- **no promueve automáticamente** ningún modelo a CHAMPION.

## Ejecución con doble clic

Desde Windows:

```bat
scripts\RUN_MEDALLIO_AI.bat
```

El BAT usa Docker si Docker Desktop está disponible. Si no lo está, cae automáticamente al `.venv` local.

Perfiles manuales:

```bat
scripts\RUN_MEDALLIO_AI.bat hourly
scripts\RUN_MEDALLIO_AI.bat daily
scripts\RUN_MEDALLIO_AI.bat weekly
scripts\RUN_MEDALLIO_AI.bat full
```

`auto` es el perfil por defecto. Ejecuta `hourly` siempre, `daily` solo una vez por fecha Lima y `weekly` una vez por semana ISO.

Para forzar Python local aunque Docker esté activo:

```bat
set MEDALLIO_AI_FORCE_LOCAL=1
scripts\RUN_MEDALLIO_AI.bat
```

Para reconstruir la imagen después de cambios de dependencias/código:

```bat
set MEDALLIO_AI_REBUILD=1
scripts\RUN_MEDALLIO_AI.bat
```

## Instalar la tarea automática

```bat
scripts\INSTALL_MEDALLIO_AI_TASKS.bat
```

Esto crea o reemplaza una única tarea de Windows:

```text
Medallio - AI Runtime
```

Se dispara cada hora. `MultipleInstances=IgnoreNew` evita duplicados y el runtime además usa un advisory lock PostgreSQL para coordinar ejecuciones iniciadas desde Windows, Docker o consola.

Para eliminarla:

```bat
scripts\INSTALL_MEDALLIO_AI_TASKS.bat remove
```

## Coordinación con el DW

Antes de iniciar modelos, el runtime comprueba el advisory lock `medallio.dw_refresh`. Si el DW está refrescando, devuelve `DW_REFRESH_BUSY` y termina correctamente. La tarea horaria volverá a intentarlo en el siguiente ciclo.

El propio runtime usa `medallio.ai_runtime`, por lo que un doble clic no puede duplicar una corrida ya activa.

## Docker

La imagen es `medallio-ai:local` y el servicio está en `compose.ai.yml`.

El contenedor:

- ejecuta el mismo paquete `replica_cygnus` del repositorio;
- monta `artifacts/`, `logs/` y `.medallio/` para persistencia;
- usa `.env` en runtime, no durante el build;
- cambia `POSTGRES_HOST` a `host.docker.internal` por defecto para alcanzar PostgreSQL de Windows;
- no incluye `.env`, conversaciones, Excel/CSV ni artefactos locales en el build context.

Si PostgreSQL no vive en el host de Docker, definir antes de ejecutar:

```bat
set MEDALLIO_DOCKER_POSTGRES_HOST=nombre-o-ip-del-host
```

## Estado y logs

Estado de cadencias:

```powershell
.\.venv\Scripts\python.exe scripts\medallio_ai_runtime.py status
```

Plan sin ejecutar:

```powershell
.\.venv\Scripts\python.exe scripts\medallio_ai_runtime.py plan --profile auto
```

Logs:

```text
logs/medallio_ai_runtime.log
```

Estado persistente:

```text
.medallio/ai_runtime_state.json
```

## Principio de gobierno

La automatización sí puede capturar datos, entrenar, evaluar, predecir y medir. No puede auto-promover un challenger. La promoción de CHAMPION continúa usando el flujo explícito de Lead Scoring y requiere aprobación humana.
