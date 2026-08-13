from pathlib import Path
import os
import psycopg

ROOT=Path(__file__).resolve().parents[2]
p=ROOT/".env"
if p.exists():
    for raw in p.read_text(encoding="utf-8").splitlines():
        s=raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k,v=s.split("=",1)
            os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))

with psycopg.connect(
    host=os.getenv("POSTGRES_HOST","localhost"),
    port=int(os.getenv("POSTGRES_PORT","5432")),
    dbname=os.getenv("POSTGRES_DATABASE","medallio_dw"),
    user=os.getenv("POSTGRES_USER","postgres"),
    password=os.getenv("POSTGRES_PASSWORD",""),
    sslmode=os.getenv("POSTGRES_SSLMODE","prefer"),
) as c:
    c.execute("CALL analytics.run_absorption_phase_b_qa()")
    c.commit()
    rows=c.execute("""
        SELECT check_name,severity,failed_rows,status,checked_at
        FROM observability.absorption_quality_results
        ORDER BY checked_at DESC,quality_result_id DESC
        LIMIT 20
    """).fetchall()
    for r in rows:
        print(r)
