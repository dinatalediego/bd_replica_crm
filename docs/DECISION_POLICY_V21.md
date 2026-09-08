# Decision Policy V2.1 — Frozen Cohort Contract

Decision system: `priorizacion_leads`  
Policy: `lead_priority_v2_1`  
Version: `2.1`

## Why V2.1 exists

V2 proved that scoring, banding, capacity selection and recommendation materialization work, but a recurring notebook could re-select Control entities and the pilot lacked an immutable run identity. V2.1 makes the pilot a governed cohort instead of a rolling selection.

## Contract

```text
serving scores
  -> LIVE + PENDING + A/B + lookback
  -> exclude prior governed assignment
  -> exclude prior V2/V2.1 recommendation exposure
  -> select cohort once
  -> exact deterministic allocation
  -> persist assignments
  -> freeze cohort
  -> Treatment recommendation only
  -> human action
  -> matured outcome
  -> ITT / learning
```

## Identity

Three identifiers are deliberately separate:

- `experiment_id`: causal experiment identity.
- `policy_run_id`: immutable execution/cohort identity.
- `run_key`: human-readable key such as `pilot_01`.

`policy_run_id` is deterministic from `experiment_id + run_key`, so retrying the same run is idempotent rather than creating a new cohort.

## Frozen cohort

`experiments.policy_runs` stores the run contract and targets.  
`experiments.policy_run_assignments` stores the point-in-time assignment snapshot.

A run can be frozen only when all three gates hold:

- cohort count equals `cohort_size`;
- Treatment count equals `treatment_target_n`;
- Control count equals `control_target_n`.

After `FROZEN`, assignment rows are immutable by trigger. Protected run configuration is also immutable.

## Exact allocation

For a 100-lead pilot with `treatment_share=0.80`:

```text
Treatment = 80
Control   = 20
```

The cohort is selected by:

1. priority band A before B;
2. `priority_score` descending;
3. `decision_at` descending;
4. `evidence_key` stable tie-breaker.

Treatment/Control assignment is deterministic from a SHA-256 hash of `policy_run_id + evidence_key`, sorted once, then cut at the exact target count.

## No re-entry

V2.1 excludes:

- entities already present in any governed `policy_run_assignments` for `priorizacion_leads`;
- entities already present in legacy `experiments.assignments` for this decision system;
- entities with prior `lead_priority_v2` or `lead_priority_v2_1` recommendations.

Within an experiment, `UNIQUE (experiment_id, entity_id)` is the hard database constraint that prevents Control or Treatment from entering another run.

## Control protection

Only Treatment may receive a V2.1 recommendation. Before a run becomes `ACTIVE`, the service checks that no Control recommendation exists for the `policy_run_id`.

`experiments.v_policy_run_status.control_clean` must be true.

## Legacy V2 reconciliation

Existing V2 recommendations are not deleted. They are exposed by:

```sql
SELECT *
FROM experiments.v_policy_legacy_recommendations;
```

Rows without `policy_run_id` are preserved for audit but are not action-ready under the V2.1 contract.

## Install

```powershell
git pull
python scripts/install_decision_policy_v21.py
```

Expected validation:

```text
Tables:    2 / 2
Views:     4 / 4
Functions: 3 / 3
```

## Dry-run preview

```powershell
python scripts/run_decision_policy_v21.py preview --run-key pilot_01
```

Expected target for a full pilot:

```text
selected: 100
CONTROL      20
TREATMENT    80
```

## Freeze

Only after preview is correct:

```powershell
python scripts/run_decision_policy_v21.py freeze --run-key pilot_01
```

Then inspect:

```powershell
python scripts/run_decision_policy_v21.py status --run-key pilot_01
```

Required action gate:

```text
status               FROZEN
cohort_n             100
Treatment             80
Control               20
exact_allocation_ok   true
control_clean         true
action_ready          true
```

## Recommendations

After the frozen cohort is validated:

```powershell
python scripts/run_decision_policy_v21.py recommend --run-key pilot_01
```

Expected recommendation count: 80. The run moves from `FROZEN` to `ACTIVE`.

## Power BI

Two additional semantic blocks are installed:

- `analytics.v_pbi_policy_runs`
- `analytics.v_pbi_policy_run_assignments`

Use them to show cohort identity, exact Treatment/Control counts, frozen status, contamination and action readiness.

## Causal language

V2.1 protects the experimental assignment. It does not by itself prove causal impact. Causal interpretation still requires protocol adherence, outcome maturity, balance review, contamination review and the chosen estimand (currently ITT).
