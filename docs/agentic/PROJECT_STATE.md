# Project State — bd_replica_crm

Last reviewed for MAP initialization: 2026-09-30

## Purpose

This repository is the Medallio data/analytics codebase around the CRM replica and downstream analytics layers.

## Verified from the current repository README

The current default-branch README identifies the repository state as:

- MEDALLIO — Absorption Mart / Fase C Core v0.1.0;
- PostgreSQL analytics marts for Power BI;
- canonical sales based on reconciled commercial-cycle data;
- stock derived from effective physical transitions;
- explicit absorption metrics and stock-month calculations;
- a warning against scheduling full `TRUNCATE + INSERT` refreshes hourly.

This file intentionally does not attempt to summarize every feature branch.

## Forecasting robustness branch — 2026-10-04

FORECAST-ROBUSTNESS-002 extends the merged forecasting pilot from PR #39.
The branch adds guarded validation policies, equal-population comparisons,
inventory coverage, temporal support checks, source fingerprints and stricter
as-issued outcome measurement. Reconstructed history remains diagnostic;
confirmation requires future frozen results. See ADR-015 and ACTIVE_TASK.md.

The FORECAST-BI-003 follow-up documents three distinct unit review cases in
NP/SL/TZ (repeated in the supplied monthly panel) and adds read-only
diagnostics plus Power BI import queries/measures. It does not certify the source
records or rewrite existing forecast runs. See ADR-016 and ACTIVE_TASK.md.

## Current MAP status

MAP v1.0 is being introduced as a coordination layer only.

It does **not** change:

- Redshift query frequency;
- ETL semantics;
- schemas;
- Power BI contracts;
- business definitions.

## Repository truth rule

When this snapshot becomes stale, update it from verified repository/runtime evidence rather than from remembered conversation context.

## Important operational principle

Agentic coordination must remain cheaper and safer than the work it coordinates:

- compact docs;
- no duplicated chat transcripts;
- no secrets;
- no production PII;
- no automatic push/merge from the handoff utility.
