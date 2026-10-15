# Medallio Forecast Factory v1.0.3

## Evidence Calendar + Automated Maturity Evaluator + Model Scoreboard

v1.0.3 does not create a new forecast model.

It operationalizes the evidence lifecycle created by v1.0.2.

```text
forecast issued
      ↓
evidence calendar
      ↓
target month closes
      ↓
actual loader
      ↓
scope compatibility
      ↓
maturity evaluator
      ↓
canonical evaluation
      ↓
model scoreboard
      ↓
challenger recommendation
      ↓
HUMAN champion approval
```

---

# 1. Why the evaluation sample matters

v1.0.2 can contain several vintages predicting the same:

```text
model
× project
× target month
```

Counting every correlated vintage as an independent observation could make the
sample appear much larger than it really is.

v1.0.3 uses:

```text
LATEST_WITHIN_MODEL_PROJECT_TARGET_LEAD_BUCKET
```

Therefore one evaluation sample is kept for each:

```text
model version
× project
× target month
× lead-time bucket
× evidence class
```

The raw forecasts remain untouched.

---

# 2. Evidence Calendar

Views:

```text
analytics.v_forecast_evidence_calendar_detail_v103
analytics.v_forecast_evidence_calendar_v103
```

The calendar answers:

```text
When does evidence unlock?
How many evaluation candidates should mature?
How many projects and models are represented?
How many are still incubating?
How many are blocked by scope?
How many were evaluated?
```

Typical CEO output:

```text
Next evidence unlock: 2026-12-01
Expected candidate pairs: ...
Current champion: NOT_YET_DECLARED
```

---

# 3. Automated Maturity Evaluator

The evaluator:

1. reruns the v1.0.2 monthly adapter idempotently;
2. reloads closed actual months;
3. refreshes scope compatibility;
4. selects mature evaluation candidates;
5. writes `analytics.forecast_evaluation_v1`;
6. records `MATURE_OUTCOME` evidence;
7. updates prediction status to `EVALUATED`;
8. refreshes the scoreboard automatically.

Run manually:

```powershell
python .\scripts\forecast_factory_v103.py run-cycle --trigger-source MANUAL
```

It is safe to run repeatedly.

Actual corrections are handled by v1.0.2's actual revision ledger and the
evaluation row is recalculated on the next cycle.

---

# 4. Evaluation intervals remain honest

Monthly increment intervals are still incubating.

Therefore v1.0.3 changes:

```text
forecast_evaluation_v1.interval_hit
forecast_evaluation_v1.interval_width
```

to allow `NULL`.

This means Medallio can legitimately reach:

```text
point forecast evidence = PASS
uncertainty evidence = INCUBATING
```

without inventing confidence bands.

---

# 5. Model Scoreboard

Portfolio view:

```text
analytics.v_forecast_model_scoreboard_portfolio_v103
```

Project view:

```text
analytics.v_forecast_model_scoreboard_project_v103
```

Metrics include:

```text
mature pairs
distinct target periods
distinct projects

WAPE
Bias
Naive WAPE
Skill vs Naive

Interval Coverage
```

The important addition is **temporal breadth**.

A model cannot become promotion-ready merely because it generates many
cross-sectional predictions for one month.

Portfolio policy requires at least:

```text
3 distinct mature target months
3 projects
6 mature pairs
WAPE <= 25%
Skill vs Naive > 0
|Bias| <= 15%
```

These are policy thresholds and can be changed later.

---

# 6. Champion is never automatic

View:

```text
analytics.v_forecast_challenger_recommendation_v103
```

can return:

```text
NOT_YET_DECLARED
READY_FOR_HUMAN_REVIEW
CHAMPION_DECLARED
```

But no model is automatically promoted.

Approved champions live in:

```text
model_control.forecast_champion_registry_v103
```

The system recommends.

A human approves.

This prevents a temporary statistical winner from silently becoming the
business forecasting standard.

---

# 7. Maturity cycle observability

Every automated run is logged in:

```text
model_control.forecast_maturity_cycle_v103
```

including:

```text
cycle status
actual rows before / after
mature candidates
evaluation count
new evidence rows
latest actual period
next evidence unlock
```

This is the beginning of MLOps-style observability for the forecast evidence
pipeline.

---

# 8. Install

Copy the package over `bd_replica_crm` and run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\86_install_forecast_factory_v103.ps1
```

This installs the schema and immediately runs the first evidence cycle.

Then:

```powershell
python .\scripts\forecast_factory_v103.py status
```

---

# 9. Optional Windows automation

The daily cycle script is:

```text
scripts/87_run_forecast_evidence_cycle.ps1
```

Test it manually first:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\87_run_forecast_evidence_cycle.ps1
```

Only after that succeeds, optionally register the Windows task:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\88_register_forecast_evidence_task.ps1
```

Default:

```text
Medallio - Forecast Evidence Cycle
daily 06:15
```

Custom time:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\88_register_forecast_evidence_task.ps1 `
  -At "07:10"
```

Daily is intentionally sufficient.

Forecast maturity changes slowly; checking every hour would add noise without
meaningful evidence value.

---

# 10. Power BI

New stable surfaces:

```text
analytics.v_pbi_forecast_evidence_calendar_v103
analytics.v_pbi_forecast_model_scoreboard_v103
analytics.v_pbi_forecast_project_scoreboard_v103
analytics.v_pbi_forecast_champion_status_v103
analytics.v_pbi_forecast_ceo_evidence_status_v103
analytics.v_pbi_forecast_maturity_cycles_v103
```

The existing detailed monthly forecast surface remains:

```text
analytics.v_pbi_forecast_monthly_current_v102
```

Recommended page:

```text
PREDICTIVE EVIDENCE
```

Top row:

```text
Prospective forecasts
Evaluated pairs
Next evidence unlock
Expected pairs next unlock
Champion status
```

Middle:

```text
Evidence Calendar
```

Bottom:

```text
Model × Lead-Time Scoreboard
```

---

# 11. What should happen right now

Given the v1.0.2 state shown before this package, the expected first state is
approximately:

```text
evaluated prospective pairs = 0
next evidence unlock = 2026-12-01
scoreboard = empty
champion = NOT_YET_DECLARED
```

That is a successful result.

The system must not create a winner before reality has arrived.

When November closes, a scheduled cycle should automatically:

```text
load November actuals
        ↓
resolve compatible scope
        ↓
mature eligible forecasts
        ↓
calculate errors
        ↓
persist evidence
        ↓
populate first scoreboard cells
```

After multiple target months mature, the promotion gate begins to have enough
temporal evidence to recommend a challenger.
