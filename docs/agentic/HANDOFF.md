# Latest Handoff

Protocol: MEDALLIO AGENT PROTOCOL 1.0
Generated at: 2026-10-12T19:15:00-05:00
Task: TEMPORAL-DS-001 — Medallio Temporal Science Factory — macro/micro forecasting closed loop
From: chatgpt
To: human
Status: IMPLEMENTED_NEEDS_LOCAL_VALIDATION
Branch: feat/temporal-inference-factory
Base: main @ a1ebb3cff4d053fd78b19af4799346d73cb1a4a8

## Exact next action

En el PC con Medallio actualizado, cambiar a esta rama y ejecutar:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_temporal_science.py
.\.venv\Scripts\python.exe scripts\temporal_science.py init
.\.venv\Scripts\python.exe scripts\temporal_science.py profile
.\.venv\Scripts\python.exe scripts\temporal_science.py status
.\.venv\Scripts\python.exe scripts\temporal_science.py run
```

Si todo pasa, marcar el PR listo para review/merge. Instalar la tarea Windows sólo
después del run manual satisfactorio:

```powershell
powershell -NoProfile -File .\scripts\68_install_temporal_science_task.ps1
```

## Scope implemented

- nuevos schemas `forecasting_control`, `forecasting_macro`, `forecasting_micro`;
- perfiles de distribución y tiempo por run/serie/variable;
- router de familias de forecasting con prerequisitos explícitos;
- drift PSI/mean shift y señales de reentrenamiento;
- vistas macro reconstruidas y vistas observadas point-in-time;
- probabilidad micro de venta a 30/60/90/180 días;
- validación micro temporal con embargo y Brier contra baseline;
- coordinación con el robust `commercial_forecasting` ya existente;
- CLI, instalador Windows, pruebas y documentación de arquitectura.

## Safety

Implementación aditiva: no modifica RAW, CORE, Phase B, ventas canónicas, absorción,
pricing ni el flujo horario. No agrega consultas Redshift. No se hizo merge a `main`.
Las tablas de evidencia nuevas son append-only donde corresponde.

## Validation / limits

No se ejecutó PostgreSQL real ni se pobló el esquema local desde esta sesión. No se
reclama que `tests/test_temporal_science.py` haya pasado: un intento de obtener el repo
en el runtime de ejecución quedó bloqueado por DNS/red. La revisión de esta entrega fue
estructural y contra los contratos reales existentes en GitHub.

## Important semantic contract

La historia reconstruida sigue etiquetada como diagnóstico. Un predictor histórico sólo
puede tratarse como point-in-time si existía/capturó con `available_at/information_cutoff`
anterior al origen. El sistema no transforma valores actuales en historia mediante joins.

## Handoff rule

El siguiente agente debe inspeccionar el diff real, ejecutar tests y validar el SQL en
Medallio local antes de declarar el producto operativo o fusionarlo a `main`.
