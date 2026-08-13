from pathlib import Path
import os, psycopg

ROOT=Path(__file__).resolve().parents[2]
SQL=ROOT/"sql"/"30_absorption_phase_c"

def env():
    p=ROOT/".env"
    if p.exists():
        for raw in p.read_text(encoding="utf-8").splitlines():
            s=raw.strip()
            if s and not s.startswith("#") and "=" in s:
                k,v=s.split("=",1)
                os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))

def connect():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST","localhost"),
        port=int(os.getenv("POSTGRES_PORT","5432")),
        dbname=os.getenv("POSTGRES_DATABASE","medallio_dw"),
        user=os.getenv("POSTGRES_USER","postgres"),
        password=os.getenv("POSTGRES_PASSWORD",""),
        sslmode=os.getenv("POSTGRES_SSLMODE","prefer"),
    )

def main():
    env()
    files=[
        "00_prerequisites.sql",
        "01_metric_definitions.sql",
        "02_tables.sql",
        "04_qa.sql",
        "03_refresh_full.sql",
        "08_current_views.sql",
        "05_indexes.sql",
    ]
    with connect() as c:
        for f in files:
            print("[SQL]",f)
            c.execute((SQL/f).read_text(encoding="utf-8"))
            c.commit()
    print("Fase C Core instalada.")

if __name__=="__main__":
    main()
