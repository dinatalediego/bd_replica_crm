# Medallio v2.8.4 — Pre-Maturity Control & Decision Execution Readiness

## Por qué ahora

v2.8.3 ya logró el activo esencial: forecasts prospectivos reales e inmutables.
Pero L3 no puede madurar hasta que cierre el primer target.

No conviene llenar ese tiempo con nuevos modelos ni suavizar el gate.
Conviene gobernar dos frentes:

1. calidad de la evidencia que está incubando;
2. convertir decisiones existentes en acción→outcome→aprendizaje.

## Qué aclara 84 vs 70

La vista nueva clasifica cada captura en:

- PROSPECTIVE_ELIGIBLE
- CURRENT_PERIOD_NOWCAST
- LATE_OR_RETROSPECTIVE

Así CEO deja de interpretar `capturados` como `forecasts prospectivos activos`.

También controla:

- benchmark coverage;
- horizon alignment;
- model/version/run traceability;
- data cutoff;
- prediction negativa;
- prediction por encima del stock.

Esto NO promueve L3.

## Decision execution loop

Se crea una cola de ejecución sobre los ledgers existentes:

```text
Decision
→ Owner
→ Deadline
→ Action
→ Outcome
→ Mature Outcome
→ Learning
```

Estados:

- NEEDS_OWNER
- NEEDS_DEADLINE
- NEEDS_ACTION
- ACTION_IN_PROGRESS
- WAITING_OUTCOME
- OUTCOME_IMMATURE
- LEARNING_COMPLETE

## Instalación

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\75_install_pre_maturity_control.ps1
```

## Artifacts

```text
pre_maturity_control_v284.json
forecast_issue_quality_exceptions_v284.csv
decision_execution_gap_v284.csv
07_pre_maturity_control.png
08_execution_learning_loop.png
```

## Cómo interpretar

El estado ideal durante incubación es algo similar a:

```text
pre_maturity_status=READY_TO_INCUBATE
active=70
incubating=70
benchmark_coverage=100%
next_maturity=2026-12-01
```

Mientras L3 espera, el trabajo humano pasa a la cola de decisiones.
La primera decisión que debería convertirse en acción controlada es la de mayor prioridad ejecutiva que tenga owner claro y una métrica medible.
