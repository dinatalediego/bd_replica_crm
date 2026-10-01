# Active Task

Task ID: NIGHT-001  
Title: Bootstrap Night Shift OS and restore green CI  
Status: IMPLEMENTING  
Owner: chatgpt  
Next agent: claude  
Branch: feat/medallio-night-shift-os  
Base branch: main

## Objective

Turn MAP into a governed overnight production pilot for 2026-10-01 through 2026-10-07, while fixing the current root CI dependency gap.

## Scope

- Night Shift protocol;
- seven-day queue;
- autonomy/safety policies;
- resource budget guards;
- morning-report template;
- deterministic local validation/status/next-task CLI;
- tests for queue contracts;
- minimal CI dependency fix for `matplotlib`.

## Explicit non-scope

- no automatic merge to main;
- no production deploy;
- no destructive DB migration;
- no additional Redshift polling;
- no Claude API spend;
- no attempt to invent unknown repositories.

## Evidence already observed

The first MAP PR was merged to main.

GitHub CI failed during test collection because `replica_cygnus.pricing_study.service` imports `matplotlib.pyplot` while the CI installation `.[dev]` did not install matplotlib.

## Acceptance criteria

- [x] Night Shift queue/policies/budgets/week plan defined;
- [x] queue validation/status/next-task CLI implemented;
- [x] queue tests added;
- [x] dev dependency includes matplotlib for pricing-study test collection;
- [ ] GitHub CI passes on this branch;
- [ ] first morning-report flow is proven;
- [ ] Claude or human performs adversarial review before merge.

## Next action

Wait for GitHub CI on the draft PR, resolve only evidence-backed failures, then hand NIGHT-001 to Claude/human review.
