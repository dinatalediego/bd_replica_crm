from pathlib import Path
import os, psycopg
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
    c.execute("CALL analytics.refresh_absorption_phase_c_full()")
    c.commit()
    print("Fase C backfill completado.")
