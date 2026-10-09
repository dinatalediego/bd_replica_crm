# Medallio v2.9.3 — Action Execution Evidence + Intervention Ledger

## What this version fixes

v2.9.2 proved that MD and MT were human-approved and activated.

v2.9.3 refuses to treat that as proof that the business action actually occurred.

It separates:

```text
APPROVED CONTRACT
        ↓
EXECUTION EVIDENCE
        ↓
OUTCOME EVIDENCE
        ↓
LEARNING
```

MD and MT are bootstrapped as:

```text
SCHEDULED
```

not `STARTED`.

## New PostgreSQL objects

```text
decision_intelligence.intervention_ledger_v293
decision_intelligence.intervention_event_v293
decision_intelligence.intervention_cost_v293
decision_intelligence.intervention_evidence_v293

decision_intelligence.v_intervention_monitoring_v293
decision_intelligence.v_intervention_event_timeline_v293
decision_intelligence.v_intervention_cost_summary_v293

analytics.v_pbi_ai_control_tower_v293
analytics.v_pbi_outcome_roi_v293
analytics.v_pbi_project_deep_dive_v293
analytics.v_pbi_predictive_evidence_v293
analytics.v_ai_control_tower_v293
```

## Install

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\80_install_action_execution_evidence.ps1
```

Expected first state:

```text
MD | execution=SCHEDULED | health=READY_TO_START | outcome_sla=WAITING_OUTCOME
MT | execution=SCHEDULED | health=READY_TO_START | outcome_sla=WAITING_OUTCOME
```

This is correct.

## When Modena actually starts

Do not run this because the contract exists.
Run it on the real business start date.

```powershell
python .\scripts\intervention_ledger_v293.py start `
  --project MD `
  --actor "Diego" `
  --date 2026-10-XX `
  --note "Intervención realmente iniciada; alcance validado con Comercial + Pricing."
```

Then:

```text
SCHEDULED → STARTED
```

## When implementation is materially in market

```powershell
python .\scripts\intervention_ledger_v293.py implemented `
  --project MD `
  --actor "Diego" `
  --note "Pricing/commercial action fully implemented in the agreed scope."
```

## Evidence

Examples:

```powershell
python .\scripts\intervention_ledger_v293.py attach-evidence `
  --project MD `
  --actor "Diego" `
  --evidence-type "PRICING_CHANGE" `
  --source-reference "analytics / approved price list / internal record" `
  --note "Evidence of implemented pricing change."
```

Evidence references are metadata/pointers; PostgreSQL remains the ledger.

## Costs

```powershell
python .\scripts\intervention_ledger_v293.py record-cost `
  --project MD `
  --actor "Diego" `
  --date 2026-10-XX `
  --category "COMMERCIAL_INCENTIVE" `
  --amount 10000 `
  --source-reference "internal budget / validated source"
```

Recommended cost categories:

```text
PAID_MEDIA
COMMERCIAL_INCENTIVE
DISCOUNT_MARGIN_COST
EVENT_ACTIVATION
AGENCY
MATERIALS
OTHER_DIRECT
```

Use economic incremental cost, not only invoices.

## Scope changes

If the real action differs materially from what was approved, evidence it:

```powershell
python .\scripts\intervention_ledger_v293.py scope-change `
  --project MD `
  --actor "Diego" `
  --file .\path\to\new_scope.json `
  --reason "Business-approved material scope change."
```

This does not rewrite the frozen contract; it records divergence from it.

## Completion

```powershell
python .\scripts\intervention_ledger_v293.py complete `
  --project MD `
  --actor "Diego" `
  --date 2026-XX-XX `
  --note "Execution completed; contract now waits for outcome maturity."
```

## Monitoring architecture

Recommended architecture now:

```text
PostgreSQL / Medallio DW
       │
       ├──────── Power BI
       │         CEO / Management / recurring corporate reporting
       │
       └──────── Python / Streamlit
                 analyst exploration / QA / ML diagnostics / rapid iteration
```

### Why not "MLOps instead of a dashboard"?

MLOps solves a different problem:

```text
training
model registry
deployment
feature/serving consistency
drift
model monitoring
experimentation
```

It should eventually feed the Control Tower, not replace it.

### Recommended division

**Power BI**
- executive control tower;
- project portfolio;
- decision/execution SLA;
- outcome/ROI;
- Power BI-native filters and distribution.

**Python / Streamlit**
- experimental analysis;
- model diagnostics;
- econometric plots;
- cohort/feature exploration;
- rapid QA before promoting metrics to Power BI.

**MLOps later**
- when Medallio has multiple production models that train/score regularly;
- registry, model versions, drift, champion/challenger, deployment health.

## Optional Streamlit starter

```powershell
streamlit run .\apps\medallio_ai_control_tower_v293.py
```

It reads the same PostgreSQL views as Power BI.

## Power BI starter

Files:

```text
powerbi/starter_queries.sql
powerbi/starter_measures.dax
config/dashboard_contract_v293.json
```

Recommended first pages:

```text
01 CEO Control Tower
02 Decision & Execution
03 Outcome & ROI
04 Predictive Evidence
05 Project Deep Dive
```

The semantic source of truth is PostgreSQL.
Do not duplicate business logic in both Power BI and Python if it can live safely in SQL.
