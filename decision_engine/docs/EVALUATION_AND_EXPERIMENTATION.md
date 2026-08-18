# Evaluation & Experimentation Standard

## Principle

A risk model is not useful because it predicts well in aggregate. It is useful if ranking the cases it selects causes better commercial outcomes under real capacity constraints.

For `separation_fall_risk`, evaluation has three layers:

1. **data correctness** — the entity was truly eligible at decision time;
2. **predictive/ranking quality** — high-priority cases are more likely to fall without conversion;
3. **decision value** — acting on recommendations improves conversion / reduces falls net of cost.

---

## 1. Unit of analysis

Canonical unit:

`codigo_proforma + codigo_unidad + decision_observed_at`

Operational entity id:

`separation:<separacion_source_id>`

Do not evaluate at client-only or project-only grain because a client can participate in more than one commercial opportunity.

---

## 2. Eligibility must be reconstructed point-in-time

At each historical `decision_observed_at`, an entity can be scored only if information known at that instant implies:

- lifecycle open;
- separation active;
- no active Entrega;
- proforma within 3 calendar months;
- no dated payment evidence available;
- no confirmed payment marker available;
- no positive initial-payment amount available;
- all required keys resolved.

Any event recorded after `decision_observed_at` is forbidden as a feature.

Outcome events after `decision_observed_at` are allowed only as labels.

---

## 3. Outcome definitions

### Primary 30-day label

`fall_30d = 1` when a valid CAIDA occurs within 30 days after decision time and before confirmed conversion.

`fall_30d = 0` when the opportunity converts or remains open through the horizon without a qualifying fall.

Censoring must be explicit when the observation window has not completed.

### Secondary outcomes

- `conversion_30d`;
- `days_to_conversion`;
- `days_to_fall`;
- `still_open_30d`;
- `economic_value_30d` where price/margin is available.

For survival modelling, conversion and fall should be treated as competing events rather than silently flattening all censored observations.

---

## 4. Baselines that every model must beat

### B0 — Random eligible ranking

Sanity floor.

### B1 — Separation age only

Order descending by `days_since_separation`.

### B2 — Contact gap only

Order descending by `days_since_last_interaction`.

### B3 — Current rule baseline

Current explainable points policy.

### Challenger

Any ML/survival/uplift model must be compared out-of-time against B1–B3.

---

## 5. Temporal validation

Never use random train/test split as the primary evaluation.

Recommended initial design:

- training: oldest available complete cohorts;
- validation: next contiguous period;
- test: latest complete horizon;
- rolling-origin evaluation as data volume grows.

All preprocessing parameters must be learned only from the training period.

Project launches/closures and commercial-regime changes should be visible in cohort analysis.

---

## 6. Ranking metrics under capacity

Commercial capacity is finite; therefore top-K metrics are more meaningful than global accuracy.

Report at K = 10, 20, 30 and realistic daily capacity:

- precision@K for fall;
- recall@K;
- lift@K vs eligible base rate;
- conversion@K after intervention when operational data exists;
- average days-to-event among selected cases;
- project/advisor concentration.

For probabilistic models also report:

- Brier score;
- calibration curve / calibration error;
- PR-AUC when falls are relatively rare;
- ROC-AUC only as a secondary diagnostic.

---

## 7. Segment robustness

A model cannot be promoted on aggregate performance alone.

Minimum slices:

- project;
- advisor;
- proforma age bucket;
- separation age bucket;
- interaction-data availability;
- unit type;
- calendar cohort.

Flag any segment with materially worse calibration, excessive false positives or insufficient support.

Small samples should be labelled insufficient rather than overinterpreted.

---

## 8. Shadow evaluation

Shadow mode builds forward-looking evidence without influencing the commercial team.

For every shadow snapshot retain:

- policy version;
- feature contract version;
- observed_at;
- candidate universe and exclusions;
- rank / score / action;
- project and advisor;
- subsequent outcome.

After the 30-day horizon, compute metrics as they would have been observed prospectively.

This is the cleanest bridge from baseline rules to a defensible model evaluation dataset.

---

## 9. Pilot experiment

Once shadow results are stable, use a human-in-the-loop experiment.

### Preferred design

Randomize at an entity level only if contamination is manageable. If advisors alter behavior across all their pipeline after seeing recommendations, randomize by advisor-period or use a staggered design.

Possible variants:

- Control: current commercial process;
- Treatment: prioritized worklist + explanation.

Primary metric:

- conversion before fall / conversion within horizon.

Guardrails:

- no increase in complaints;
- no harmful discounting;
- workload per advisor;
- contact saturation;
- margin protected.

Pre-register hypothesis, unit, metric, horizon and stopping logic in `decision_intelligence.experiment_registry` before exposure.

---

## 10. Value equation

Start simple and make assumptions explicit.

Example:

`incremental_value = incremental_conversions * contribution_margin - incremental_contact_cost - incentive_cost`

For risk triage, also report:

`value_per_reviewed_case`

and

`value_per_commercial_hour`

because a policy that creates more sales but consumes disproportionate sales capacity may still be inferior.

---

## 11. Promotion criteria

A challenger can replace the baseline only when:

- point-in-time contract passes;
- it improves the decision-relevant metric out-of-time;
- calibration is adequate if probabilities are exposed;
- no critical cohort materially degrades without justification;
- operational latency/cost is acceptable;
- shadow execution is stable;
- business owner understands the change;
- rollback is available.

If the challenger does not beat the rule baseline, keep the simpler rule.

---

## 12. What not to optimize

Do not optimize for:

- maximum number of recommendations;
- maximum model complexity;
- accuracy on the full population when the business only acts on top-K;
- retrospective fit using future information;
- a metric that cannot be translated into an operational or economic consequence.

The target is **better decisions under constraints**, not a prettier model report.
