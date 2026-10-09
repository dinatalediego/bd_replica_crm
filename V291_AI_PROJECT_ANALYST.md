# Medallio v2.9.1 — AI Project Analyst + Decision Contract Generator

## Qué cambia

v2.9.0 construyó contexto gobernado por proyecto.

v2.9.1 convierte ese contexto en dos salidas:

1. **AI Project Analyst**
   - clasifica el tipo de problema de cada proyecto;
   - calcula prioridad relativa;
   - separa evidencia observada, predictiva y de ejecución;
   - formula preguntas e hipótesis;
   - genera un briefing por proyecto.

2. **Decision Contract Draft**
   - propone un tipo de contrato;
   - congela baseline;
   - sugiere owner y métrica;
   - deja `deadline = NULL`;
   - deja `success_criterion = TO_DEFINE_EX_ANTE`;
   - nunca activa automáticamente una decisión.

## Portfolio activo incluido

```text
MD, MT, CP, NP, SL, EEUU, GY, FX, TZ
```

Editable en:

```text
config/active_portfolio_v291.json
```

## Arquetipos

```text
EXECUTION_CONTRACT
DATA_RECONCILIATION
VALUE_CAPTURE_DESIGN
ABSORPTION_DIAGNOSIS
DIAGNOSTIC_TO_PREDICTIVE
CLOSEOUT_OPTIMIZATION
CLOSEOUT_LEARNING
PORTFOLIO_OPTIMIZATION
MONITOR
```

La intención es que Medallio no trate a los nueve proyectos como el mismo problema.

## Objetos SQL

```text
analytics.project_ai_analysis_snapshot_v291
analytics.v_project_ai_analysis_latest_v291
analytics.v_active_portfolio_priority_v291

decision_intelligence.project_decision_contract_draft_v291
decision_intelligence.v_decision_contract_review_queue_v291
```

## Artefactos

```text
artifacts/project_ai_analyst_v291/
    active_portfolio_command_center.md
    active_portfolio_priority.csv

    MD/
      analysis.json
      ai_project_brief.md
      decision_contract_draft.json

    MT/
    CP/
    ...
```

## Regla de seguridad empresarial

Los contratos se crean siempre como:

```text
DRAFT_REVIEW_REQUIRED
```

y deliberadamente NO se inventa:

```text
deadline
action_cost
expected_roi
success threshold
causal claim
```

Esos campos requieren dueño humano o evidencia real.

## Instalación

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\77_install_ai_project_analyst.ps1
```

## Validar un proyecto

```powershell
python .\scripts\project_ai_analyst_v291.py refresh --project MD
```

## Qué revisar primero

1. `active_portfolio_priority.csv`
2. `active_portfolio_command_center.md`
3. `MD/decision_contract_draft.json`
4. `MT/decision_contract_draft.json`
5. proyecto clasificado como `DATA_RECONCILIATION`
6. proyectos clasificados como `CLOSEOUT_*`

## Próximo paso

Tras validar los drafts con negocio:

```text
v2.9.2 — Human Approval + Contract Activation + Outcome SLA
```

Ahí recién un draft aprobado podría convertirse en decisión activa con deadline, métrica,
baseline y plan de captura de outcome.


## Corrección de Evidence Ceiling incluida

La revisión de los bundles detectó un punto importante:

```text
MD / MT mostraban highest_claim_level = OUTCOME
```

pero el propio `v_decision_outcome_status` mostraba:

```text
outcome_count = 0
latest_outcome_ts = null
outcome_status = NO_OUTCOME
```

La causa era que v2.9.0 interpretaba la existencia de una fila de status
como si fuera un outcome observado.

v2.9.1 incluye una corrección del compiler v2.9.0:

```text
NO_OUTCOME status row != observed outcome
```

Por tanto MD y MT deben permanecer, por ahora, en:

```text
PREDICTIVE_INCUBATING
```

hasta que exista `outcome_count > 0`.

El instalador refresca primero los contextos con esta regla corregida.
