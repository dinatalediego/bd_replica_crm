# Medallio v2.7.4 — Runtime Reliability Hotfix

The v2.7.3 run proved the important business milestone:

```text
altitude=L2 Diagnóstico & Comparabilidad
next=PREDICTIVE BLOCK
```

So L2 is now genuinely unlocked.

This patch fixes the two remaining runtime defects.

## Fix 1 — db_sync false connection error

Observed:

```text
db_sync={
  enabled: True,
  status: ERROR:RuntimeError:
  No se pudo abrir PostgreSQL...
}
```

But the same run had already read 17 project states from PostgreSQL.

Root cause:

`medallio_db_connection()` wrapped the `yield` inside a broad `try/except`.

Therefore an SQL error occurring AFTER a successful connection was incorrectly
re-labelled as a connection error.

v2.7.4:
- only wraps actual connection creation;
- SQL errors preserve their true exception/message;
- checks required persistence relations before writing;
- if schema v2.7 is not installed, returns:

```text
SKIPPED_SCHEMA_NOT_INSTALLED
```

instead of a misleading database connection error.

## Fix 2 — Google Sheets Decimal is not JSON serializable

PostgreSQL numeric columns arrive through psycopg as:

```python
Decimal
```

Google's Python client ultimately runs:

```python
json.dumps(body)
```

which cannot serialize Decimal.

Every Sheets cell is now normalized:

```text
Decimal integer -> int
Decimal decimal -> float
date/datetime -> ISO string
numpy scalar -> Python scalar
dict/list -> JSON string
NaN/NaT -> null
```

This applies centrally in `sheet_append`, so all current and future tabs are protected.

## Slides

The v2.7.3 fix already worked.

Your log:

```text
Slides | reemplazando 3 páginas previas del slot=morning
CHANNEL OK | Slides
```

confirms idempotent replacement is now functioning.

## Validate

```powershell
python .\scripts\validate_v274_runtime_reliability.py
```

Then:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
```

Expected business state:

```text
altitude=L2 Diagnóstico & Comparabilidad
next=PREDICTIVE BLOCK
```

Finally:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning
```

Expected channels:

```text
CHANNEL OK | Drive
CHANNEL OK | Sheets
CHANNEL OK | Slides
CHANNEL OK | Docs
CHANNEL OK | Calendar
CHANNEL OK | Chat
CHANNEL OK | Gmail
```

If persistence schema is installed:

```text
db_sync.status = OK
```

If it is not installed:

```text
db_sync.status = SKIPPED_SCHEMA_NOT_INSTALLED
```

and the validator will name the missing relations.
