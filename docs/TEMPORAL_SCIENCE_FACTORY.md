# Medallio Temporal Science Factory

## Estado en `main`

La fábrica temporal se integra como **capacidad experimental y opt-in**. El código puede vivir en `main`, pero no queda habilitado por el refresh horario ni se instala ninguna tarea de Windows automáticamente.

Antes de activar una ejecución programada debe completarse la validación local contra `medallio_dw`.

## Objetivo

Convertir el forecasting en un ciclo de ciencia de datos temporal reproducible, separando de forma explícita la evidencia disponible en el tiempo `t` de la historia reconstruida posteriormente.

```text
I_t = {variables observadas o publicadas con available_at <= t}
P(Y_(t+h) | I_t)
```

Se agregan tres namespaces independientes:

- `forecasting_macro`: proyecto/portafolio y series agregadas;
- `forecasting_micro`: unidad/segmento y probabilidad de venta por horizonte;
- `forecasting_control`: perfiles, suitability, drift, model runs y señales de reentrenamiento.

No reemplaza RAW, CORE, absorción, pricing ni `commercial_forecasting`. No agrega consultas Redshift.

## Evidencia temporal

El sistema distingue:

- `OBSERVED_POINT_IN_TIME` / `PROSPECTIVE_OBSERVED`: evidencia realmente observada y congelada antes del resultado;
- `RECONSTRUCTED_REVISED_HISTORY` / `HISTORICAL_DIAGNOSTIC_SHADOW`: historia reconstruida, útil para diagnóstico pero insuficiente para afirmar qué habría sabido el modelo en el pasado.

Nunca debe transformarse una variable actual en histórica mediante un `JOIN` sin fecha de hecho y fecha de disponibilidad.

## Flujo

```text
Medallio local actualizado
        ↓
contratos temporales
        ↓
perfil estadístico y calidad
        ↓
router de familias candidatas
        ↓
validación temporal + baseline
        ↓
macro forecast + micro probability
        ↓
predicción congelada
        ↓
outcome maduro
        ↓
error / calibración / drift
        ↓
REVIEW / RETRAIN_CANDIDATE / BLOCKED
```

## Perfil y router

`forecasting_control.variable_profile` registra, según soporte disponible:

- N, faltantes y huecos;
- ceros y cuantiles;
- tendencia, autocorrelación y fuerza estacional;
- ADF/KPSS como diagnósticos;
- ADI/CV² para demanda smooth/erratic/intermittent/lumpy.

Familias consideradas según evidencia:

| Familia | Rol |
|---|---|
| Moving average 3 | baseline obligatorio |
| Seasonal naive 12 | candidato con historia suficiente |
| ETS | candidato en series regulares |
| Croston-SBA | candidato para demanda intermitente |
| SARIMAX / dynamic regression | candidato con exógenas point-in-time |
| Global tree con lags | shadow/candidato según soporte |
| Reconciliación jerárquica | shadow hasta validar niveles base |
| Micro logit | probabilidad 30/60/90/180 días |

La promoción nunca depende solo de complejidad o ajuste in-sample: exige validación temporal contra baseline.

## Micro-modelo

El micro-modelo utiliza variables de proyecto/unidad y demanda previa cuando el contrato temporal existe. El split es temporal, no aleatorio, y aplica embargo entre entrenamiento y validación.

Un challenger entrenado únicamente con historia reconstruida conserva rol `HISTORICAL_DIAGNOSTIC_SHADOW`; no puede convertirse en champion operativo.

## Drift y retraining

PSI y desplazamiento de media funcionan como señales operativas, no como pruebas científicas universales:

- PSI bajo: `NO_ACTION`;
- zona intermedia: `REVIEW`;
- drift alto: `RETRAIN_CANDIDATE`;
- huecos o contrato roto: `BLOCKED`.

Reentrenar no implica promover: el challenger vuelve a pasar por baseline y validación temporal.

## Instalación y validación local

Desde la raíz del repositorio:

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -e ".[dev]"
& $python -m pytest tests\test_temporal_science.py -q
& $python scripts\temporal_science.py init
& $python scripts\temporal_science.py profile
& $python scripts\temporal_science.py status
```

Después, para un ciclo manual completo:

```powershell
& $python scripts\temporal_science.py run
```

Solo si el ciclo real termina satisfactoriamente conviene instalar la tarea independiente:

```powershell
powershell -NoProfile -File .\scripts\68_install_temporal_science_task.ps1
```

La tarea es independiente de la réplica horaria y no se crea al fusionar el código en `main`.

## Entregables mínimos de un modelo temporal

Un run útil debe conservar:

1. Data Contract;
2. Information Set Report;
3. Distribution & Time Profile;
4. Algorithm Suitability Matrix;
5. Temporal Backtest Pack;
6. Model Card + artifacts;
7. Forecast & Uncertainty Pack;
8. Outcome/Drift/Retrain Pack.

Si faltan los primeros tres, elegir algoritmo es prematuro. Si faltan los últimos cuatro, existe un experimento de notebook pero no un producto de forecasting.

## Mejoras de datos prioritarias

- historial real de disponibilidad/bloqueo por unidad;
- snapshot diario de precio/oferta/descuento;
- contrato verificable de visitas;
- campañas con inicio/fin, inversión y `available_at`;
- contexto macro con fecha de publicación/vintage;
- jerarquía estable Portfolio → Project → Bedrooms → Typology → Unit;
- ledger de intervenciones, decisiones y outcomes.

## Principio de operación

La presencia del código en `main` **no habilita producción**. Activación, scheduling y promoción de modelos continúan sujetos a validación local, evidencia temporal suficiente y revisión humana.
