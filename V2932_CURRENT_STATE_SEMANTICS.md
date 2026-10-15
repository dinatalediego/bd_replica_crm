# Medallio v2.9.3.2 — Current-State vs Historical Semantics

## Why this patch exists

After Matera was correctly cancelled and reissued, Medallio contained two legitimate historical records:

```text
MT old contract/intervention → CANCELLED
MT new contract/intervention → SCHEDULED / READY_TO_START
```

The old row must **not be deleted** because it proves governance worked.

But it must also **not count as a current metric issue**.

v2.9.3.2 therefore separates:

```text
FULL HISTORY
decision_intelligence.v_intervention_monitoring_v293

CURRENT OPERATIONAL STATE
decision_intelligence.v_intervention_current_v2932
```

## Install

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\82_install_current_state_semantics.ps1
```

Expected current state:

```text
scheduled=2
active_execution=0
waiting_outcome=0
mature_outcomes=0
metric_issues=0

MD | absorcion_promedio_3m | OK | SCHEDULED | READY_TO_START
MT | gap_value             | OK | SCHEDULED | READY_TO_START
```

The historical audit should still show:

```text
MT | CANCELLED=1
MT | SCHEDULED=1
```

That is correct.

## Important

Do not delete the cancelled Matera rows.

They are evidence that Medallio prevented a malformed contract from reaching execution.
