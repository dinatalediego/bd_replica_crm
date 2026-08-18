from pathlib import Path
import os
import psycopg

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "sql" / "20_absorption_phase_b"

def load_env():
    p = ROOT / ".env"
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        s=raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k,v=s.split("=",1)
        os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))

def conn():
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
    files = [
        "00_prerequisites.sql",
        "01_control_and_functions.sql",
        "02_tables.sql",
        "04_qa.sql",
        "03_refresh_full.sql",
        "03b_sale_date_pago_ci.sql",
        "05_incremental.sql",
    ]
    with conn() as c:
        for name in files:
            print(f"[SQL] {name}")
            c.execute((SQL/name).read_text(encoding="utf-8"))
            c.commit()
    print("Fase B instalada.")

if __name__=="__main__":
    main()
