# Medallio v2.9.0 — Project Intelligence Context Layer + AI-Ready Dossiers

## Qué resuelve

Medallio ya puede observar el portafolio, gobernar forecasts y registrar decisiones.
El siguiente salto es que cada proyecto tenga un **contexto propio, profundo y gobernado**
que una IA pueda usar sin mezclar:

- hechos observados,
- métricas derivadas,
- evidencia predictiva,
- recomendaciones,
- outcomes,
- claims causales.

## Principio

No queremos "pasarle toda la base a una IA".

Queremos construir para cada proyecto un **Context Packet** compacto, versionado y auditable:

```text
PROJECT
  ↓
estado comercial
  ↓
historia de ventas / stock / absorción
  ↓
mix de producto / unidades
  ↓
pricing / econometría / estacionalidad
  ↓
forecast / benchmark / madurez
  ↓
decisiones / acciones / outcomes
  ↓
posición relativa en el portafolio
  ↓
hipótesis de IA
  ↓
evidence ceiling
```

## Nuevos objetos

```text
analytics.project_context_snapshot_v290
analytics.v_project_context_latest_v290
analytics.v_project_context_coverage_v290
```

## Fuentes que intenta aprovechar

El compiler usa sólo relaciones existentes y tolera fuentes faltantes:

```text
analytics.v_project_growth_state
analytics.comercial_proyecto_mes
analytics.snapshot_unidad_diario
analytics.historial_oferta_unidad
features.v_dataset_unidad_entrenamiento
analytics.v_econometria_serie_precios
analytics.v_econometria_cobertura
features.v_estacionalidad_panel
analytics.v_forecast_issue_quality_v284
analytics.v_forecast_maturity_clock_v283
analytics.v_forecast_performance_v283
analytics.v_forecast_performance_by_project_horizon
decision_intelligence.v_decision_execution_gap_v284
decision_intelligence.decision_ledger
decision_intelligence.v_decision_outcome_status
```

La ausencia de una fuente no tumba el proceso: queda registrada como `MISSING`.

## Artefactos por proyecto

Ejemplo:

```text
artifacts/project_intelligence_v290/MD/
    context.json
    brief.md
    ai_prompt.md
    source_coverage.csv
```

El `context.json` contiene evidencia compacta y perfiles de fuentes.

`brief.md` es una lectura humana.

`ai_prompt.md` establece reglas estrictas para cualquier modelo de IA.

## Reglas para IA

Cada afirmación debe etiquetarse como:

```text
[OBSERVED]
[DERIVED]
[PREDICTIVE]
[RECOMMENDED]
[OUTCOME]
```

La IA no puede:

- llamar prospectivo a un backtest;
- inventar deadlines, costo, ROI o outcomes;
- convertir correlación en causalidad;
- superar el claim level que soporta la evidencia del proyecto.

## Portfolio-relative intelligence

Cada dossier calcula percentiles del proyecto frente al portafolio para:

```text
stock
ventas
meses de cobertura
gap económico
attention score
meta
```

Esto permite preguntas mucho más útiles:

> ¿Este proyecto está mal por sí mismo o sólo parece grande porque es grande?

> ¿Está en el top quartile de riesgo de stock?

> ¿Su gap es extremo frente al resto?

## AI hypotheses

El compiler no "decide"; fabrica preguntas e hipótesis trazables como:

```text
ECONOMIC_EXPOSURE
ABSORPTION_RISK
UNIT_MIX
PREDICTIVE_EVIDENCE
EXECUTION_GAP
```

Cada hipótesis incluye:
- evidencia que la disparó,
- pregunta que debe investigar la IA/humano.

## IA sin costo adicional obligatorio

El paquete funciona sin API de IA.

Puedes generar el bundle para ChatGPT/manual:

```powershell
python .\scripts\project_ai_synthesis_v290.py `
  --project MD `
  --mode prompt-only
```

Eso crea:

```text
ai_input_bundle.md
```

Opcionalmente, si alguna vez instalas Ollama local:

```powershell
python .\scripts\project_ai_synthesis_v290.py `
  --project MD `
  --mode ollama `
  --model qwen2.5:7b
```

y crea:

```text
ai_brief.md
```

El modo Ollama es opcional y no forma parte del gate corporativo.

## Instalación

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\76_install_project_intelligence_context.ps1
```

## Piloto recomendado

Después del refresh completo:

```powershell
python .\scripts\project_intelligence_context_v290.py refresh --project MD
```

y revisar:

```text
artifacts/project_intelligence_v290/MD/brief.md
artifacts/project_intelligence_v290/MD/context.json
```

Modena es un buen primer piloto porque ya existe una decisión de pricing/comercial
y un gap de ejecución que puede convertirse en un contrato de decisión trazable.

## Qué viene después

Una vez validemos el dossier de 1–3 proyectos, el siguiente paso es:

```text
v2.9.1
AI Project Analyst + Decision Contract Generator
```

No para que la IA "mande", sino para que produzca:
- diagnóstico con evidencia,
- hipótesis,
- preguntas,
- decision contract draft,
- métricas de éxito,
- gaps de datos,
- y explicación ejecutiva.
