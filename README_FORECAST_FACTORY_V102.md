# Medallio Forecast Factory v1.0.2

## What this version adds

```text
Prospective Issuance Clock
+ Lead-Time Forecasting
+ Monthly Increment Adapter
+ Actual Loader
```

It does **not** add another forecasting algorithm.

Its job is to turn the forecasting engine that already exists into a system that
can accumulate defensible prospective evidence.

---

## 1. Monthly Increment Adapter

The existing commercial forecast is cumulative:

```text
H1 = Oct
H2 = Oct + Nov
H3 = Oct + Nov + Dec
```

v1.0.2 derives:

```text
Oct = H1
Nov = H2 - H1
Dec = H3 - H2
```

The original cumulative predictions remain untouched.

The derived target is:

```text
target_name = sales_units
aggregation_semantics = PERIOD_VALUE
scope_semantics = EXISTING_STOCK_NO_FUTURE_INFLOWS
```

### No silent clamping

If:

```text
H3 < H2
```

the resulting monthly increment would be negative.

v1.0.2 does not silently convert it to zero.

It records:

```text
REJECTED
NON_MONOTONIC_CUMULATIVE_PATH
```

in:

```text
model_control.forecast_adapter_audit_v102
```

That is useful evidence about forecast coherence.

---

## 2. Prospective classification happens at target-month level

A run emitted during October may have:

```text
October  -> SHADOW
November -> PROSPECTIVE
December -> PROSPECTIVE
January  -> PROSPECTIVE
```

A derived monthly prediction becomes `PROSPECTIVE` only if:

```text
issued_at < target month start
data_cutoff_date < target month start
```

Backtests are never upgraded.

---

## 3. Lead time

Every monthly prediction stores:

```text
lead_time_days
lead_time_months
lead_time_bucket
```

Buckets:

```text
IN_PERIOD_SHADOW
LT_1_30D
LT_31_60D
LT_61_90D
LT_91D_PLUS
```

So Medallio can eventually answer:

> Is Random Forest useful 20 days ahead but weak 80 days ahead?

rather than hiding all horizons inside one aggregate WAPE.

---

## 4. Honest monthly intervals

Cumulative interval bounds are **not** differenced.

That would ignore covariance between cumulative forecast errors.

Therefore monthly derived forecasts start as:

```text
prediction_lower = NULL
prediction_upper = NULL
interval_status = INCUBATING_MONTHLY_RESIDUAL_CALIBRATION
```

Point-forecast evidence can mature first.

Uncertainty becomes defendible later, after prospective monthly residuals exist.

---

## 5. Actual Loader

Source:

```text
analytics.v_absorcion_ventas_mensual
```

The loader automatically detects common column names for:

```text
project
period
sales
month_complete
stock_initial
stock_final
```

If it cannot safely detect a required field, it stops and prints the available
columns.

You can override detection in:

```text
config/forecast_factory_v102.json
```

Example:

```json
"column_overrides": {
  "project": "codigo_proyecto",
  "period": "periodo_mes",
  "sales": "ventas_mes"
}
```

Only complete months are loaded.

If no explicit complete-month flag exists, the conservative fallback is:

```text
period < current calendar month
```

---

## 6. Actual revisions are audited

If CRM corrections later change a closed actual:

```text
7 -> 8
```

the current canonical actual is updated, but the change is first written to:

```text
analytics.forecast_actual_revision_v102
```

No silent rewriting of evaluation truth.

---

## 7. Scope compatibility

The current legacy forecast is:

```text
EXISTING_STOCK_NO_FUTURE_INFLOWS
```

Generic observed sales are only fully comparable if no material stock inflow
occurred after forecast origin.

If the source provides:

```text
stock_initial
stock_final
sales
```

v1.0.2 computes monthly implied inflow:

```text
stock_final - stock_initial + sales
```

and sums it from origin through target month.

Statuses:

```text
COMPATIBLE
INCOMPATIBLE_INFLOW
INSUFFICIENT_STOCK_FLOW_EVIDENCE
INCOMPLETE_WINDOW
```

If stock-flow evidence is unavailable, Medallio blocks the scope rather than
pretending it is comparable.

---

## 8. Maturity Clock

Monthly predictions move through:

```text
INCUBATING
MATURE
BLOCKED_SCOPE
INVALIDATED
```

A strict mature pair requires:

```text
actual month complete
scope compatible
evidence_class = PROSPECTIVE
issued before target month start
data cutoff before target month start
```

---

## 9. Lead-Time Performance

View:

```text
analytics.v_forecast_lead_time_performance_v102
```

Produces by:

```text
model
project
lead-time bucket
lead-time months
```

the metrics:

```text
mature_pairs
WAPE
Bias
Naive WAPE
Skill vs Naive
Interval Coverage
```

---

## 10. Two separate gates

v1.0.2 deliberately separates:

```text
POINT FORECAST GATE
```

from:

```text
UNCERTAINTY GATE
```

Possible state:

```text
point_gate_status = PASS
uncertainty_gate_status = INCUBATING
overall_gate_status = POINT_PASS_INTERVAL_INCUBATING
```

That is more honest than forcing fake prediction intervals merely to satisfy a
dashboard.

---

# Install

Copy the package over the repository and run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\85_install_forecast_factory_v102.ps1
```

Or step by step:

```powershell
python .\scripts\forecast_factory_v102.py install

python .\scripts\forecast_factory_v102.py adapt-monthly

python .\scripts\forecast_factory_v102.py load-actuals

python .\scripts\forecast_factory_v102.py status
```

---

# What a strong first result looks like

Do not expect `PASS` immediately.

A useful result is more like:

```text
Adapter
  ACCEPTED=...
  REJECTED=...

Monthly predictions
  SHADOW | IN_PERIOD_SHADOW | ...
  PROSPECTIVE | LT_1_30D | ...
  PROSPECTIVE | LT_31_60D | ...

Actuals
  rows=...
  latest=2026-09-01

Maturity
  MATURE=...
  INCUBATING=...
  BLOCKED_SCOPE=...

Issuance clock
  PROSPECTIVE_INCUBATING
  next_maturity=2026-12-01
```

If older genuinely pre-issued forecasts already have closed future months, you
may immediately get some mature prospective pairs.

That is welcome, provided the scope gate also passes.

---

# Power BI surfaces

Use:

```text
analytics.v_pbi_forecast_monthly_current_v102
analytics.v_pbi_forecast_issuance_clock_v102
analytics.v_pbi_forecast_lead_time_performance_v102
analytics.v_pbi_forecast_adapter_audit_v102
```

The report can now distinguish:

```text
prediction
vs
evidence quality
vs
lead time
vs
maturity
vs
scope comparability
```

without knowing which forecasting algorithm generated the original cumulative
forecast.
