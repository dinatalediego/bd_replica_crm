# Medallio low-impact source policy

## Principle

Redshift is an upstream source, not the serving layer. Power BI, Orbita, quality,
pricing, scoring and other products should consume PostgreSQL/Medallio
(raw_cygnus -> staging -> analytics/features) whenever possible.

## Source cadence

- Scheduled source refresh: conservative 4-hour cadence.
- `REDSHIFT_SYNC_INTERVAL_HOURS` can change the source interval without code.
- Manual mode always permits an explicit source refresh.
- Local transforms may run more frequently against cached RAW data.

## Connection safety

Every multi-table sync has a Redshift Connection Gate. Authentication is tested
once before table work starts. If authentication fails or the account is locked,
the whole source sync aborts before attempting any table.

A single Redshift session is reused across tables. A reconnect is allowed only
for a genuine transient transport failure (timeout/reset), not for authentication
errors.

## Operations

While the Redshift account is locked, keep the scheduled replica task disabled.
After the DBA confirms unlock and the local .env credential is verified:

1. Run `scripts\12_diagnosticar_redshift.bat` once.
2. If it succeeds, run `scripts\06_sincronizar_habilitadas.bat`.
3. Verify with `scripts\09_ver_estado.bat`.
4. Recreate/enable the conservative scheduled task only after success.

Do not commit .env or credentials.
