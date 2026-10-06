# Latest Handoff

Task: CLIENTES-DQ-INCREMENTAL-001 — DQ incremental y recuperación de 02b
Owner: chatgpt
Next agent: human
Branch: feat/clientes-calidad-incremental
Status: REVIEW_READY
Published PR: https://github.com/dinatalediego/bd_replica_crm/pull/40

## Evidence

135 platform + 106 decision engine tests passed locally. SQL scenarios executed
in PGlite, including full parity, hashes/IDs, DQ rules, migration and rollback.
141773 synthetic rows: initial rebuild 13.7s, no-op 4.2s, one change 4.5s.
CI 37204692789: 172 passed; only concurrent test reconnect failed because
Connection.info.dsn removes passwords. Fixed by reusing disposable test DSN;
final PostgreSQL CI pending. Production code did not need changing for that failure.

## Next action

Apply PR commits while preserving local portal/config/orchestrator fixes.
Follow docs/CLIENTES_CALIDAD_INCREMENTAL.md: install schema component, run DQ
twice, enable only known commented 02b via backup/AST helper, run local DW,
then enable Scheduler and confirm next LastTaskResult=0.

## Limits and contracts

ADR-014. Compare local RAW ID/hash excluding verified ETL metadata. O(n) local
scan; transform only changes. Raw deletions propagated; no new Redshift queries.
No access to actual Medallio or Windows; real activation/performance pending.
FORECAST-EVIDENCE-001 / PR 39 keeps its own local validation pending.

## Night Shift checkpoint — NIGHT-002

Date: 2026-10-06
Branch: `feat/night-002-refresh-health-guards-v2`
Draft PR: #45
Status: REVIEW_READY
CI: PASS — GitHub Actions CI run 37267247058, run number 213, completed successfully on head `7bab14618bacbfb4695ef633963129dc5931d72b`.

The previously stranded NIGHT-002 work was reconciled onto current `main` without
bringing stale MAP state forward. The PR adds `docs/NIGHT_002_REFRESH_AUDIT.md`,
`tests/test_refresh_contract.py`, and this handoff evidence: one canonical hourly
entrypoint, exactly one `sync --due-only`, and no source sync under `--local-only`.
No polling interval, Redshift query, production data, or deployment behavior changed.

Exact next action: review Draft PR #45. If accepted, a human may decide whether to
merge it; unattended agents must not merge `main`. If review finds a concrete defect,
allow at most one evidence-backed rework cycle. Do not start another Night Shift task
while NIGHT-002 remains the in-flight pilot item. No Claude review is claimed.
