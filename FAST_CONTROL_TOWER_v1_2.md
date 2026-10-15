# Medallio Ambassador v1.2 — Fast Control Tower

## Diagnóstico del error de tu captura

El kernel `medallio_dw` ya está funcionando.

El fallo real ahora es:

```text
CellTimeoutError: A cell timed out while it was being executed, after 1200 seconds
```

y ocurre dentro de la celda `Snapshot corporativo` del Control Tower v2.

La versión original:
- perfilaba muchos objetos por separado;
- volvía a consultar varios de esos objetos;
- podía pedir hasta 250,000 filas por vista;
- y además era el notebook Enterprise completo, no sólo el dashboard.

Para un Ambassador que corre 3 veces al día, eso es demasiado.

## Solución v1.2

### Nuevo notebook
`Medallio_CEO_AI_Control_Tower_Lite.ipynb`

Contiene sólo:
- conexión;
- snapshot;
- CEO Control Tower;
- Data Foundation;
- Business Analytics;
- Econometría;
- ML readiness;
- Forecast;
- Decision Intelligence;
- Governance;
- Value;
- CEO Action Board.

No contiene el laboratorio Enterprise profundo.

### Fast snapshot
- Una sola lectura por dataset.
- 10k–50k filas como máximo según uso.
- `statement_timeout` por consulta.
- Si una vista es lenta, se omite y el resto del briefing continúa.
- El perfil de calidad se calcula en memoria, sin volver a consultar PostgreSQL.

### Timeouts por notebook
- CEO 5-Minute: 300 s
- Control Tower Lite: 360 s
- Enterprise OS: 1200 s
- Analytics Factory: 1200 s

## Instalación

1. Copia:
`notebooks/Medallio_CEO_AI_Control_Tower_Lite.ipynb`

a:
`C:\Projects\bd_replica_crm\notebooks\`

2. Reemplaza:
`scripts\medallio_ambassador\run_ambassador.py`

3. En tu `config\medallio_ambassador.json`, cambia `notebooks` y agrega
`notebook_timeouts_seconds` usando el example incluido.

## Prueba

```powershell
python scripts\medallio_ambassador\run_ambassador.py --slot morning --dry-run
```

El morning ahora debe ejecutar sólo:
- CEO 5-Minute
- Control Tower Lite

Los notebooks profundos quedan para Evening.


## Mejora de integridad del briefing

v1.2 también cambia la política de artifacts a **current-run-only**.

Si un notebook falla, el Ambassador ya no toma una imagen antigua del directorio y la
presenta como si fuera nueva. Sólo adjunta `board_summary`, decisiones e imágenes cuyo
`mtime` corresponde a la corrida actual.

Esto es importante para que un correo ejecutivo nunca mezcle evidencia fresca con
evidencia histórica sin avisarlo.
