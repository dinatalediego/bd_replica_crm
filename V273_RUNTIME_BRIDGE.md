# Medallio v2.7.3 — Runtime Bridge + Governed CEO Queue

Este hotfix corrige tres síntomas observados después de v2.7.2.

## 1. L2 seguía WARN aunque `project_growth_state.py` veía 17/17

Causa:

`project_growth_state.py` usa la conexión nativa del repo:

```python
load_settings()
connect_postgres(settings)
```

pero Ambassador v2.7.2 buscaba únicamente:

```text
DATABASE_URL / PGHOST / PGUSER / ...
```

Por eso el log mostraba:

```text
db_sync={'enabled': True, 'status': 'NO_DSN'}
```

y Ambassador no veía la vista que sí existía.

v2.7.3 usa:

```text
DSN/env si existe
↓
si no:
replica_cygnus.settings + connect_postgres
```

No necesitas duplicar credenciales.

## 2. CEO Decision Queue seguía mostrando el fallback antiguo

El notebook CEO se ejecuta ANTES del enriquecimiento Evidence/Outcome.

Por eso producía:

```text
Mantener rumbo y exigir evidencia de valor
```

antes de que Ambassador consultara:

```text
decision_intelligence.v_ceo_growth_decision_queue
```

v2.7.3 reemplaza después del enrichment:

```text
ceo_decision_queue.csv
04_ceo_decision_queue.png
```

con la cola gobernada real.

También actualiza `board_summary.json` únicamente en:
- top_3_decisions
- growth_altitude
- governed_queue

No modifica los KPI observados.

## 3. Google Slides fallaba por objectId duplicado

El error:

```text
Invalid requests[0].createSlide:
The object ID (...) should be unique among all pages and page elements.
```

venía de reutilizar IDs estables sin borrar la página previa.

Ahora:
1. obtiene la presentación,
2. identifica las 6 slides del mismo día/slot,
3. las elimina,
4. vuelve a crearlas.

Así Morning puede re-ejecutarse sin acumular duplicados ni fallar.

## Validación

Después de copiar los archivos:

```powershell
python .\scripts\validate_v273_runtime_bridge.py
```

Esperado:

```text
[DB_BRIDGE] project_states=17
[DB_BRIDGE] governed_actions=...
[DB_BRIDGE] L2 source ready: analytics.v_project_growth_state
```

Luego:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

Esperado:

```text
V2.7 | altitude=L2 Diagnóstico & Comparabilidad | next=PREDICTIVE BLOCK/WARN
```

y `db_sync` ya no debería decir `NO_DSN`.

Finalmente:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

El correo/Slides/CSV deben usar la nueva CEO queue:
- governance de outcome + ROI;
- MD;
- MT;
- CP;
- SL;
- etc., según score real.
