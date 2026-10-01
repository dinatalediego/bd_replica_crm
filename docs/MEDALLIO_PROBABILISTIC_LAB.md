# Medallio Probabilistic Lab V1

## Objetivo

Convertir Medallio en un laboratorio reproducible para estudiar Modelos
Probabilísticos de Matemática para IA con problemas del ciclo comercial
inmobiliario.

## Arquitectura

    Redshift
       ↓
    bd_replica_crm
       ↓
    medallio_dw (PostgreSQL local)
       ↓  READ ONLY
    MedallioDatasetAdapter
       ↓
    Feature Builder
       ↓
    Probability Families
       ↓
    Figures + Metrics + Story
       ↓
    PDF / Notebook

El laboratorio es downstream. No abre conexiones a Redshift y no forma parte
del task horario de réplica.

## Dataset canónico V1

Fuente inicial:

    analytics.int_ciclo_comercial_unidad

El laboratorio usa el ciclo comercial certificado en Medallio y construye
features derivadas sin escribir en la base.

## Familias

1. Bernoulli/Binomial: conversión entre ciclos con desenlace observado.
2. Beta–Binomial: incertidumbre posterior por proyecto/asesor.
3. Tiempo a evento: duración separación → venta/caída.
4. Logistic Regression + XGBoost opcional: P(venta | X), calibración y scoring.
5. Gaussian Mixture: exploración de perfiles latentes.

## Regla importante de target

Una separación todavía abierta no se etiqueta como no venta. Las familias de
conversión y clasificación supervisada usan solamente ciclos con un desenlace
observado en la V1.

Esto evita convertir censura operacional en una etiqueta negativa falsa.

## Instalación

Desde la raíz del repositorio:

    .\.venv\Scripts\python.exe -m pip install -e ".[probabilistic-lab]"

## Tests

    .\.venv\Scripts\python.exe -m pytest tests\test_probabilistic_lab.py

## Ejecución

    .\.venv\Scripts\python.exe scripts\probabilistic_lab.py run

Outputs:

    outputs/probabilistic_lab/
      figures/
      experiments/summary.json
      experiments/bayesian_conversion.csv
      reports/medallio_modelos_probabilisticos.pdf

## Notebook

Abrir:

    notebooks/07_medallio_probabilistic_models_orchestrator.ipynb

El notebook contiene orquestación; la lógica reusable permanece en
src/replica_cygnus/probabilistic_lab/.

## Extender con otra familia

1. Crear una clase que herede de ProbabilityFamily.
2. Implementar run(ctx) -> FamilyResult.
3. Registrarla en registry.py.
4. Añadir su id a configs/probabilistic_lab.yml.

El orquestador no necesita cambios.

## Evolución recomendada

V2:
- Kaplan–Meier y censura formal.
- hazard / Cox.
- horizonte fijo de conversión (30/60/90 días).
- calibración por proyecto y periodo.
- incertidumbre predictiva.
- conexión con model_control y experiments.

V3:
- incorporar precios, áreas, descuentos y stock point-in-time.
- pricing probabilístico y elasticidad.
- modelos jerárquicos por proyecto/tipología.
- integración de resultados en Órbita.
