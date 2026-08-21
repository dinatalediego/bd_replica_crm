from pathlib import Path
import os
import psycopg

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

if ENV_PATH.exists():
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

LOOKBACK_DAYS = int(os.getenv("ABSORPTION_PHASE_B_LOOKBACK_DAYS", "7"))

with psycopg.connect(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    dbname=os.getenv("POSTGRES_DATABASE", "medallio_dw"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", ""),
    sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
) as conn:
    conn.execute("CALL analytics.refresh_absorption_phase_b_incremental(%s)", (LOOKBACK_DAYS,))
    conn.execute("CALL analytics.run_sale_date_pago_ci_qa()")
    conn.commit()
    print(
        "Absorption Phase B incremental completado + QA de evidencia de conversión. "
        f"lookback_days={LOOKBACK_DAYS}"
    )
