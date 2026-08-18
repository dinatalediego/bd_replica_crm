# Interaction Feature Contract v0

Status: **DISCOVERY / NOT CERTIFIED**.

The mature 30-day benchmark found modest out-of-time signal using only structural and temporal features. The next feature family to certify is historical customer interaction behavior. This document deliberately defines gates before SQL feature engineering so that interaction features cannot improve metrics through temporal leakage or many-to-many join inflation.

## Source under discovery

`raw_cygnus.interacciones`

No event timestamp, event identity, or business join key is assumed until profiling is complete.

Run:

```powershell
python .\scripts\profile_interaction_contract.py
```

Outputs are written to `reports/interaction_contract_discovery/`.

## Non-negotiable temporal rule

Every behavioral feature for historical snapshot `T` must use only source interaction events whose certified business-event timestamp is `<= T`.

An ETL ingestion timestamp, row update timestamp, or extraction timestamp must not be substituted for the original business-event time unless source profiling proves that it is semantically the event time.

## Required certification gates

1. **Event time** — identify one authoritative interaction event timestamp and quantify nulls, min/max dates, impossible future values, and coverage by year/month.
2. **Entity linkage** — identify how an interaction belongs to a customer, proforma, or separation. Any bridge through `procesos` must prove that one source interaction is not multiplied across unrelated proformas.
3. **Interaction identity** — certify a stable event key or composite key and reconcile duplicate groups.
4. **Historical completeness** — profile coverage through time. Do not interpret sparse early history as low engagement.
5. **As-of safety** — point-in-time tests must prove `max(interaction_event_at_used) <= snapshot_at` for every training row.
6. **Current/historical parity** — definitions used by the live candidate feature view and historical training features must be semantically equivalent.
7. **Incremental value** — behavioral features are promoted only if a mature grouped out-of-time benchmark improves over the structural-only benchmark on PR-AUC / ranking lift without unacceptable calibration or subgroup instability.

## Candidate features after certification

Initial features should remain interpretable:

- `days_since_last_interaction`
- `interaction_count_7d`
- `interaction_count_14d`
- `interaction_count_30d`
- `active_days_with_interaction_30d`
- `interaction_channel_diversity_30d`
- `interaction_velocity_7d_vs_30d`

Possible later features may distinguish inbound/outbound, contact result, channel, advisor activity, and interaction sequence, but only after the underlying semantics are certified.

## Leakage examples that must BLOCK

- counting an interaction that occurred after `snapshot_at`;
- using a final CRM status that is only populated after fall/conversion;
- joining one customer interaction to every historical proforma for that customer without a valid temporal/business attribution rule;
- using `fecha_actualizacion` merely because it is available when it is actually an edit timestamp;
- imputing missing historical interactions as zero before proving source completeness for that period.

## Promotion sequence

`DISCOVERY -> CONTRACT CERTIFIED -> POINT-IN-TIME FEATURE BUILD -> MATURE OOT BENCHMARK -> DAILY RISK-SET BACKTEST -> SHADOW`

Do not tune model hyperparameters aggressively before this feature family is certified. The current mature benchmark is a structural baseline against which behavioral incremental value must be measured.
