# NIGHT-002 Refresh Audit

Canonical scheduled path: `scripts/run_hourly.bat` -> `scripts/dw_refresh.py --mode hourly` -> `replica_cygnus.cli sync --due-only` -> local Medallio transforms -> `replica_cygnus.cli watch`.

Verified repository guards: due-state is read from local PostgreSQL before Redshift is opened; no due sources means zero Redshift connections; a PostgreSQL advisory lock prevents concurrent Gate runs; due sources reuse one Redshift session except after transient transport failure; incremental sources default to a four-hour gate; full-refresh sources default to a 24-hour gate; `watch` reads PostgreSQL only; `--local-only` omits source synchronization.

Existing deterministic tests already cover no-due/no-connection, lock-denied/no-connection, due-subset synchronization, single-session reuse, Watch without source credentials, local-only behavior, and the single master entrypoint.

Operational rule: do not add a second scheduled sync for Orbita and do not schedule deep observability as an hourly monitor. Orbita should consume Medallio/PostgreSQL. Do not reduce gate intervals merely to make dashboards look fresher.

Safe health command: `.\\.venv\\Scripts\\python.exe -m replica_cygnus.cli watch --additional-config config/hourly_required_tables.yml`.

Safe local-processing command: `.\\.venv\\Scripts\\python.exe .\\scripts\\dw_refresh.py --local-only`.

Conclusion: the canonical path is already low-impact by design. NIGHT-002 should harden and verify this contract, not introduce a new Redshift query path. Runtime access to the user's Windows databases is intentionally outside this unattended cloud run; repository CI is the validation boundary.
