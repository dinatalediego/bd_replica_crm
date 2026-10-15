# Medallio v2.9.3.1 — Monitoring Semantics

This patch should be installed before MD or MT is marked STARTED.

## Fixes

### 1. Outcome phase semantics

Before:
```text
SCHEDULED + contract SLA → WAITING_OUTCOME
```

After:
```text
SCHEDULED    → NOT_STARTED
STARTED      → NOT_STARTED
IMPLEMENTED  → NOT_STARTED
COMPLETED    → WAITING_OUTCOME / OUTCOME_IMMATURE / OUTCOME_MATURE
```

The original v2.9.2 contract SLA remains available as `contract_sla_status`,
but the business monitoring field becomes `outcome_phase_status`.

### 2. Executive KPI semantics

Top cards become:

```text
Scheduled interventions
Active executions
Waiting outcomes
Mature outcomes
```

### 3. Atomic primary metric rule

Each active contract must have exactly one primary metric.

Good:
```text
absorcion_promedio_3m
gap_value
cumplimiento_actual
```

Bad:
```text
gap_value y cumplimiento_actual
```

The patch does not mutate a frozen active contract.

If a contract is flagged:
```text
COMPOSITE_PRIMARY_METRIC
```

do not START it.

Correct governance:
```text
cancel old contract
→ create/reissue draft
→ select one primary metric
→ keep the other as secondary
→ approve
→ activate
→ bootstrap intervention
```

### 4. Streamlit deprecation warning

The new app uses:
```python
width="stretch"
```
instead of:
```python
use_container_width=True
```

## Install

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\81_install_monitoring_semantics.ps1
```

Then run:

```powershell
python .\scripts\monitoring_semantics_v2931.py status
```

and:

```powershell
streamlit run .\apps\medallio_ai_control_tower_v2931.py
```

## What to expect now

If MD is valid:
```text
MD | SCHEDULED | READY_TO_START | outcome_phase=NOT_STARTED
```

If MT still has a composite primary metric:
```text
MT | SCHEDULED | BLOCKED_METRIC_SEMANTICS | outcome_phase=NOT_STARTED
```

Do not mark MT STARTED until that contract has been reissued.

## Power BI next front

Included:
```text
powerbi/ai_control_tower_v1_blueprint.json
powerbi/ai_control_tower_v1_measures.dax
```

The first corporate page should answer:
```text
What needs my attention now?
```

using PostgreSQL views as the semantic source of truth.


## v2.9.3.1.1 View Compatibility Hotfix

PostgreSQL does not allow `CREATE OR REPLACE VIEW` to change the name/order of existing columns. The first v2.9.3.1 SQL inserted semantic columns in the middle of existing views, so PostgreSQL interpreted `success_criterion` as being renamed to `primary_metric_is_atomic` and rolled back the transaction.

This hotfix preserves all original v2.9.3 columns in the same order and appends new semantic columns only at the end.

Run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\81b_fix_monitoring_semantics_view_compat.ps1
```
