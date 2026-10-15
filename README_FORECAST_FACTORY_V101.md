# Forecast Factory v1.0.1 — Horizon Semantics + Legacy Bridge

The empty v1 factory is healthy.

Before populating it, this patch resolves two semantic mismatches between the
canonical contract and Medallio's existing `commercial_forecasting` engine.

## Why the patch is necessary

The existing engine does not produce a simple one-month point forecast only.

It stores:

```text
origin
horizon 1..6
prediction
```

where `prediction` is **cumulative sales of the current stock through that
horizon**.

Therefore:

```text
H1 + H3 + H6
```

must never be summed.

v1.0.1 makes this explicit with:

```text
aggregation_semantics = CUMULATIVE_WINDOW
origin_period
forecast_window_start
forecast_window_end
scope_semantics
```

## Honest uncertainty

The existing engine deliberately leaves forecast intervals empty when there is
insufficient mature temporal error support.

Forecast Factory v1 originally made intervals NOT NULL.

That would create pressure to invent certainty.

v1.0.1 fixes the contract:

```text
interval may be NULL
```

and classifies the run as:

```text
INTERVAL_INCUBATING
```

until real evidence exists.

## Evidence classes

```text
PROSPECTIVE
BACKTEST
SHADOW
```

`SHADOW` means the forecast exists and is useful for monitoring, but it is not
allowed to masquerade as strict prospective evidence.

## Legacy bridge

The bridge reads the existing:

```text
model_control.commercial_forecast_runs
analytics.commercial_forecast_predictions
analytics.commercial_forecast_outcomes
```

and maps them into the canonical Forecast Factory.

Existing candidate models are preserved.

For the bridge:

```text
mean3
```

is the explicit naïve benchmark.

## Install and bridge

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\84_install_forecast_factory_v101_legacy_bridge.ps1
```

Then:

```powershell
python .\scripts\forecast_factory_v101_legacy_bridge.py status
```

The operation is idempotent.

## Power BI

Use:

```text
analytics.v_pbi_forecast_factory_current_v101
analytics.v_pbi_forecast_performance_v101
```

These surfaces make target/window semantics explicit and prevent a cumulative
forecast from being presented as a monthly point forecast.

## Next step after the bridge

Do not add more models first.

Run one new real issuance using the existing forecasting engine, then verify:

```text
run contract = PASS or INTERVAL_INCUBATING
evidence = PROSPECTIVE
maturity = INCUBATING
naive benchmark = mean3
```

As actual windows mature, the factory will begin producing:

```text
WAPE
Bias
Naive WAPE
Skill vs Naive
Interval Coverage
Defendability
```

Only then should champion/challenger promotion become operational.
