# Medallio Temporal Science Factory

## Objetivo

Esta capa convierte el forecasting en un **sistema de ciencia de datos temporal**, no en un notebook aislado. Se apoya en los contratos existentes (`evolucion_comercial`, `econometric_datasets` y `commercial_forecasting`) y agrega tres namespaces independientes:

- `forecasting_macro`: portafolio/proyecto, stock, ventas y estados agregados.
- `forecasting_micro`: unidad, dormitorio/tipología y probabilidad de venta por horizonte.
- `forecasting_control`: perfiles, suitability de algoritmos, drift, modelos, señales de reentrenamiento y evidencia de cada corrida.

No reemplaza RAW, CORE, Phase B, absorción, pricing ni el forecasting comercial ya publicado. No agrega consultas a Redshift. La instalación y ejecución usan PostgreSQL local de Medallio.

## El contrato matemático: información disponible al tiempo t

Para un origen `t`, el objetivo es estimar una distribución de `Y(t+h)` usando únicamente el conjunto de información disponible en ese momento:

```text
I_t = {variables observadas o publicadas con available_at <= t}
P(Y_(t+h) | I_t)
```

Por eso se separan dos clases de evidencia:

1. `OBSERVED_POINT_IN_TIME` / `PROSPECTIVE_OBSERVED`: observaciones realmente capturadas y congeladas antes del desenlace.
2. `RECONSTRUCTED_REVISED_HISTORY` / `HISTORICAL_DIAGNOSTIC_SHADOW`: historia reconstruida hoy. Sirve para aprender, explorar y diseñar, pero no para afirmar qué habría sabido el modelo en el pasado.

Nunca se convierte una variable actual en una variable histórica por simple `JOIN`. Precio, demanda, estado, campaña, bloqueo o contexto macro necesitan fecha del hecho **y** fecha en que la observación estuvo disponible.

## Ciclo cerrado

```text
Medallio local actualizado
        ↓
contratos temporales / information sets
        ↓
perfil de distribuciones y calidad
        ↓
router de algoritmos
        ↓
validación temporal + baseline
        ↓
macro forecasting + micro probability
        ↓
predicción congelada
        ↓
outcome maduro
        ↓
error / calibración / drift
        ↓
señal REVIEW / RETRAIN_CANDIDATE / BLOCKED
        ↺
```

El modelo macro reutiliza `commercial_forecasting`, que ya conserva snapshots, rolling origins, holdout final, baseline, selección conservadora, intervalos, artifacts y outcomes congelados. La nueva capa micro agrega una probabilidad de venta de unidad a 30/60/90/180 días con validación temporal y embargo.

## Arquitectura de datos

### Macro

`forecasting_macro.v_project_month`

- grano: proyecto × mes;
- target inicial: `ventas_mes`;
- stock inicial/final, absorción, exposición y revisiones;
- histórico explícitamente reconstruido.

`forecasting_macro.v_portfolio_month`

- grano: portafolio × mes;
- coherencia para reconciliación jerárquica.

`forecasting_macro.v_project_day_observed`

- grano: proyecto × fecha de snapshot;
- se construye solo con `analytics.snapshot_unidad_diario` realmente capturado;
- base para acumular historia point-in-time desde ahora.

### Micro

`forecasting_micro.v_unit_training`

- grano: unidad × corte × horizonte;
- predictores de unidad disponibles al corte;
- demanda de las cuatro semanas completas previas cuando existe;
- target `venta_vigente` cuando la ventana ya maduró;
- `elegible_validacion_prospectiva` conserva el gate del dataset econométrico.

`forecasting_micro.v_segment_month`

- proyecto × dormitorio × tipología × mes;
- permite pasar de “¿cuántos departamentos venderé?” a “¿qué mezcla de 1/2/3 dormitorios y tipologías explica/produce ese total?”.

`forecasting_micro.unit_sale_probability`

- predicciones emitidas append-only;
- sin PII;
- cada fila conserva origen, horizonte, information cutoff, modelo y nivel de evidencia.

## Perfil estadístico que se guarda

`forecasting_control.variable_profile` registra, por serie/variable/run:

- N, faltantes y huecos de calendario;
- proporción de ceros;
- media, desviación, min/max;
- p05/p25/p50/p75/p95;
- skewness y kurtosis;
- autocorrelación lag 1 y lag 12;
- pendiente temporal;
- fuerza estacional STL cuando hay soporte;
- ADF y KPSS como diagnósticos, no como oráculos;
- ADI y CV² para clasificar demanda `SMOOTH`, `ERRATIC`, `INTERMITTENT` o `LUMPY`.

Los perfiles micro usan el último snapshot observado para describir distribuciones de dormitorios, área, precio relativo, edad y señales de demanda sin duplicar cada unidad por horizonte.

## Router de algoritmos

El router no elige por moda ni por complejidad. Decide qué familias **merecen ser comparadas** según soporte y forma de los datos. La promoción siempre requiere validación temporal contra baseline.

| Familia | Cuándo entra | Rol inicial |
|---|---|---|
| Moving average 3 | ≥3 observaciones | baseline obligatorio |
| Seasonal naive 12 | ≥24 meses completos | candidato |
| ETS | ≥8 meses, sin huecos, ceros no extremos | candidato |
| Croston-SBA | demanda intermitente/lumpy, ≥12 meses | candidato |
| Dynamic regression / SARIMAX | ~36 meses + variables exógenas point-in-time | candidato |
| Global tree con lags | historias regulares y soporte conjunto multi-proyecto | shadow |
| Reconciliación jerárquica | modelos base validados en niveles portfolio/proyecto/segmento | shadow |
| Micro logit | unidades maduras, fecha de corte y target 30/60/90/180 | candidate/shadow |

La capa actual registra Croston/SARIMAX/global/hierarchical como familias que deben entrar al benchmark cuando exista soporte. No se presentan como implementadas si todavía no fueron entrenadas.

## Micro-modelo implementado

`micro_logit` usa:

- proyecto;
- tipología;
- dormitorios;
- estado de construcción;
- área y área relativa;
- precio relativo point-in-time cuando existe;
- edad comercial;
- mes calendario;
- leads, proformas, interacciones y visitas previas cuando su contrato existe.

Reglas:

- preferir `OBSERVADO` prospectivo;
- si todavía no hay ≥200 filas observadas maduras en ≥4 cortes, puede aprender de `RECONSTRUIDO`, pero queda `HISTORICAL_DIAGNOSTIC_SHADOW`;
- split por fecha, nunca random rows;
- embargo: el outcome de entrenamiento debe haber terminado antes de iniciar validación;
- baseline = tasa base del training;
- challenger = logistic regression regularizada y escalada;
- se selecciona el challenger solo si su Brier ≤98% del baseline y validación tiene ≥50 filas;
- un challenger entrenado solo con historia reconstruida nunca obtiene rol operativo `CHAMPION`.

El objetivo no es declarar causalidad. Es una probabilidad predictiva calibrable para priorizar/integrar el forecast.

## Drift y reentrenamiento

Para `ventas_mes` se compara la ventana reciente de seis meses contra hasta doce meses anteriores:

- PSI <0.10: normal;
- 0.10–0.25: `REVIEW`;
- ≥0.25 o desplazamiento de media muy grande: `RETRAIN_CANDIDATE`;
- huecos temporales: `BLOCKED`.

PSI es una señal operativa, no una prueba científica universal. Reentrenar no significa promover: el challenger vuelve a pasar por validación temporal y baseline.

## Qué debe entregar el sistema para escoger bien un algoritmo

Un run útil no termina con “modelo X”. Debe producir ocho piezas:

1. **Data Contract**: grano, target, frecuencia, universo, fecha de evento y fecha disponible.
2. **Information Set Report**: exactamente qué variables pertenecían a `I_t`; reconstruidas y observadas separadas.
3. **Distribution & Time Profile**: tablas de `variable_profile`, huecos, ceros, outliers, tendencia, autocorrelación, estacionalidad, ADI/CV².
4. **Algorithm Suitability Matrix**: `model_suitability` con elegibilidad, score, razones y prerequisitos.
5. **Temporal Backtest Pack**: rolling/expanding origins, embargo, población comparable, baseline/challengers, MAE/WAPE/Brier/log-loss según target.
6. **Model Card + Artifacts**: features, rangos, periodos de training/validation, evidencia, código/modelo persistido, limitaciones.
7. **Forecast & Uncertainty Pack**: predicción por origen/horizonte, intervalos/calibración cuando hay soporte y jerarquía coherente.
8. **Outcome/Drift/Retrain Pack**: resultados maduros congelados, error, sesgo, calibración, drift y acción sugerida.

Si faltan 1–3, escoger “el mejor algoritmo” es prematuro. Si faltan 5–8, un modelo puede funcionar en notebook pero no es un producto de forecasting.

## Mejoras de arquitectura que elevan la calidad de data

Prioridad alta:

1. **Historial real de disponibilidad/bloqueo por unidad.** Hoy una parte del pasado es reconstruida; esto mejora stock y exposición point-in-time.
2. **Snapshot diario de precio/oferta/descuento efectivo.** Lista, ofertado y cierre separados; nunca retrorellenar precio actual.
3. **Contrato de visitas real.** `interacciones.fecha_creacion` no equivale automáticamente a visita; configurar etiquetas/fecha del evento verificadas.
4. **Marketing/campañas con `started_at`, `ended_at`, inversión y `available_at`.** Sin eso no usar campaña como regresor causal ni predictivo histórico.
5. **Calendario de feriados/eventos** generado y versionado; permite distinguir estacionalidad calendario de edad del proyecto.
6. **Contexto macro con publicación/vintage.** Tasa hipotecaria, inflación, empleo/actividad y mercado inmobiliario deben guardar fecha de publicación; usar el vintage conocido en `t`.
7. **Jerarquía estable** `PORTFOLIO → PROJECT → BEDROOMS → TYPOLOGY → UNIT`, con IDs persistentes, para reconciliar pronósticos y evitar totales incoherentes.
8. **Ledger de intervenciones/decisiones/outcomes.** Forecast no prueba impacto; esta capa permite luego uplift/causalidad.

Prioridad media:

- calidad/frescura por fuente como feature gate, no solo log;
- data dictionary versionado con owner y SLA;
- pruebas de invariantes temporales: no future joins, labels maduros, snapshots inmutables;
- monitoreo de cobertura por proyecto/tipología, no solo total portafolio;
- conformal/quantile calibration cuando existan suficientes forecasts prospectivos independientes;
- comparación por utilidad económica además de error una vez exista coste de sobre/sub-pronóstico.

## Instalación segura

Primero traer la rama y ejecutar desde el repositorio:

```powershell
git fetch origin
git switch feat/temporal-inference-factory
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\temporal_science.py init
.\.venv\Scripts\python.exe scripts\temporal_science.py profile
.\.venv\Scripts\python.exe scripts\temporal_science.py status
```

`profile` no llama al entrenamiento macro. Para un ciclo completo manual:

```powershell
.\.venv\Scripts\python.exe scripts\temporal_science.py run
```

Esto perfila, intenta los micro-modelos elegibles y luego llama al `commercial_forecasting.py run --once-per-month` existente. Si el macro falla, la evidencia temporal/micro queda guardada y el run se marca `PARTIAL`; no se oculta el fallo.

Después de validar un ciclo real, instalar la tarea diaria independiente:

```powershell
powershell -NoProfile -File .\scripts\68_install_temporal_science_task.ps1
```

Por defecto corre 10:45, `StartWhenAvailable`, usuario actual, una sola instancia. No reemplaza la tarea horaria de réplica. Para otro horario:

```powershell
powershell -NoProfile -File .\scripts\68_install_temporal_science_task.ps1 -At '11:15'
```

## Consultas de control

```sql
SELECT * FROM forecasting_control.v_system_status ORDER BY started_at DESC;
SELECT * FROM forecasting_control.v_latest_profiles ORDER BY series_key, variable_name;
SELECT * FROM forecasting_control.v_latest_model_suitability ORDER BY series_key, suitability_score DESC;
SELECT * FROM forecasting_control.drift_metric ORDER BY created_at DESC;
SELECT * FROM forecasting_control.retraining_signal ORDER BY created_at DESC;
SELECT * FROM forecasting_micro.v_unit_sale_evaluation WHERE maduro;
```

## Estado de validación de esta rama

La implementación incluye pruebas unitarias para profiling, router, PSI y micro split/modelo. En la sesión que creó la rama no hubo acceso de red desde el runtime de pruebas para clonar GitHub ni acceso a tu PostgreSQL local, por lo que **no se afirma que esas pruebas o la migración hayan sido ejecutadas aquí**. La PR debe permanecer separada de `main` hasta ejecutar los comandos de validación en un entorno con el repositorio y/o Medallio local.
