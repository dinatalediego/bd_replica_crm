# Active Task

Task ID: TEMPORAL-DS-001
Title: Medallio Temporal Science Factory — macro/micro forecasting closed loop
Status: IMPLEMENTED_NEEDS_LOCAL_VALIDATION
Owner: chatgpt
Next agent: human
Branch: feat/temporal-inference-factory
Base branch: main

## Goal

Convertir el forecasting de Medallio en un producto de ciclo cerrado gobernado por
información disponible al tiempo t: perfiles de distribución/temporalidad, router de
algoritmos, forecasting macro reutilizando el producto robusto actual, probabilidad
micro de venta por unidad, outcomes, drift y señales de reentrenamiento.

## Result

Implementación aditiva y aislada en `forecasting_macro`, `forecasting_micro` y
`forecasting_control`. No modifica RAW, CORE, Phase B, ventas canónicas, absorción,
pricing ni contratos Power BI existentes. No agrega acceso Redshift.

Incluye:

- contrato SQL y vistas macro/micro;
- registro de corridas, series, perfiles, suitability, modelos, drift y retraining;
- profiling estadístico/temporal con ACF, STL, ADF/KPSS, ADI/CV2 y PSI;
- router de familias baseline/ETS/seasonal-naive/Croston/SARIMAX/global/hierarchy;
- micro probability 30/60/90/180 días con split temporal, embargo y Brier vs baseline;
- coordinación con `commercial_forecasting.py run --once-per-month` para el macro;
- CLI, tarea Windows opt-in, documentación y pruebas unitarias nuevas.

## Validation

La rama se construyó desde `main` commit `a1ebb3c` y sólo agrega archivos nuevos más
este estado MAP. No se ejecutaron las pruebas ni PostgreSQL real desde esta sesión:
el runtime disponible no pudo clonar por DNS y no tiene acceso al Medallio local del
usuario. Por ello no se afirma PASS de tests, migración ni población real.

Validación local mínima:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_temporal_science.py
.\.venv\Scripts\python.exe scripts\temporal_science.py init
.\.venv\Scripts\python.exe scripts\temporal_science.py profile
.\.venv\Scripts\python.exe scripts\temporal_science.py status
```

Después, ejecutar un ciclo completo manual:

```powershell
.\.venv\Scripts\python.exe scripts\temporal_science.py run
```

## Next action

Revisar el draft PR y ejecutar la validación local anterior. Si SQL/tests/run real
pasan, convertir el PR a ready, integrar a `main` y recién entonces instalar
`scripts\68_install_temporal_science_task.ps1`. No fusionar automáticamente mientras
la validación de Medallio real siga pendiente.
