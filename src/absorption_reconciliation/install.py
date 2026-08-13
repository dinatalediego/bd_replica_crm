from pathlib import Path
import os
import psycopg

ROOT=Path(__file__).resolve().parents[2]
SQL=ROOT/"sql"/"21_absorption_reconciliation"

def load_env():
    p=ROOT/".env"
    if not p.exists():
        return
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
    load_env()
    with connect() as c:
        for f in ["00_views.sql","01_qa.sql"]:
            print(f"[SQL] {f}")
            c.execute((SQL/f).read_text(encoding="utf-8"))
            c.commit()
        c.execute("CALL analytics.run_absorption_reconciliation_qa()")
        c.commit()
    print("Fase B v0.2 reconciliation instalada.")

if __name__=="__main__":
    main()
