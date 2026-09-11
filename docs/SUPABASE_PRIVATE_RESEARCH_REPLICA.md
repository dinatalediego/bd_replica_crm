# Supabase Private Medallio Research Replica

## Purpose

Copy the physical tables from local `medallio_dw` into private Supabase schemas so the research project can run remote SQL diagnostics without exposing client data through the Data API.

This is a **research replica**, not a new operational source of truth.

## Ownership

- Local `medallio_dw`: operational source of truth.
- `bd_replica_crm`: owns source semantics and data engineering.
- Supabase `medallio_*`: private research snapshot.
- `pa_pricing_in_peru`: owns research questions, econometrics, findings and RAG.

## Privacy boundary

The target schemas are not in `public`, and the bootstrap migration explicitly revokes schema usage from:

- `anon`
- `authenticated`
- `service_role`
- `PUBLIC`

The raw replica may contain PII because the user requested the complete Medallio dataset. Research-facing objects must be built separately in `medallio_research` and must omit direct identifiers.

Do not expose any `medallio_*` schema in Supabase Data API settings.

## Target schema mapping

| Local | Supabase private |
|---|---|
| raw_cygnus | medallio_raw_cygnus |
| raw_mercado | medallio_raw_mercado |
| staging | medallio_staging |
| core | medallio_core |
| analytics | medallio_analytics |
| etl_control | medallio_etl_control |
| features | medallio_features |
| decision_intelligence | medallio_decision_intelligence |
| model_control | medallio_model_control |
| experiments | medallio_experiments |
| observability | medallio_observability |

Audit metadata lives in `medallio_admin`. Thesis views will live in `medallio_research`.

## One-time prerequisites

1. Apply `sql/90_supabase_research_replica/00_private_zone.sql` to the intended Supabase project.
2. Have a current Supabase Postgres connection string. Do not commit it.
3. Have the local Medallio PostgreSQL connection string. Do not commit it.

Use a current Supabase credential. Do not reuse any credential that has previously been committed to source control.

## Environment variables — PowerShell

```powershell
$env:MEDALLIO_DSN="postgresql://USER:PASSWORD@localhost:5432/medallio_dw"
$env:SUPABASE_DB_URL="postgresql://..."
```

## Dry run first

```powershell
python scripts\sync_medallio_to_supabase.py --dry-run
```

This only discovers physical source tables and prints the mapping.

## Initial copy

```powershell
python scripts\sync_medallio_to_supabase.py
```

The script:

1. opens the Medallio source as a read-only transaction;
2. discovers physical tables;
3. creates target tables only when missing;
4. streams rows with PostgreSQL COPY;
5. compares source and target row counts;
6. records every table in `medallio_admin`.

It intentionally does **not** recreate source indexes, foreign keys, grants, triggers or views. Those are not required for a research snapshot and could couple the systems.

## Safety behavior

The sync script never executes DROP, TRUNCATE or DELETE.

If a target table is already populated, it stops instead of overwriting data.

To continue an interrupted initial load:

```powershell
python scripts\sync_medallio_to_supabase.py --resume
```

`--resume` skips only tables whose source and target counts already match. A non-empty mismatch stops for manual review.

## Test a small subset first

Recommended:

```powershell
python scripts\sync_medallio_to_supabase.py --only raw_mercado.unidades_historial
```

Then:

```powershell
python scripts\sync_medallio_to_supabase.py --only raw_cygnus.proforma_unidad --only raw_cygnus.proformas
```

Validate these before the full upload.

## What happens after upload

The next phase creates PII-free research views in `medallio_research`:

1. longitudinal list-price history;
2. repricing events;
3. quoted/negotiated price history;
4. discounts;
5. stock/lifecycle outcomes;
6. price-to-market bridge with the Peruvian Real Estate Longitudinal Data Engine.

Only after those views reconcile do we build the econometric panel for T1.
