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
