# Active Task

Task ID: NIGHT-002  
Title: Medallio low-impact refresh health checks  
Status: IN_PROGRESS  
Owner: chatgpt  
Next agent: claude  
Branch: feat/night-002-refresh-health-guards  
Base branch: main

## Objective

Audit the canonical Medallio refresh path for low-impact Redshift usage and add observability/tests without increasing source load.

## Prior task evidence

NIGHT-001 is complete:

- Night Shift OS merged through PR #35;
- GitHub CI run 181 completed successfully;
- the previous matplotlib collection failure was fixed by installing the required dev dependency;
- the seven-day dispatcher and morning-report automations are configured for the pilot.

## Constraints

- do not increase Redshift polling frequency;
- prefer Medallio/local replica evidence;
- no production DB writes;
- no merge to main from unattended execution;
- at most one automatic rework cycle;
- leave a draft PR or justified blocker.

## Acceptance criteria

- canonical refresh entrypoint documented;
- health/watch evidence exists;
- no new high-frequency Redshift query path;
- tests or deterministic validation added.

## Next action

A refresh-contract regression test and audit are committed. Open a draft PR and use GitHub CI as the validation boundary; do not claim tests pass before CI.
