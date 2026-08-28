from pathlib import Path
import os
import psycopg

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "sql" / "40_unit_semantics"


def load_env():
    p = ROOT / ".env"
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def connect():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DATABASE", "medallio_dw"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
    )


def main():
    load_env()
    with connect() as c:
        for f in [
            "00_objects.sql",
            "01_refresh.sql",
            "03_current_stock_snapshot.sql",
        ]:
            print(f"[SQL] {f}")
            c.execute((SQL / f).read_text(encoding="utf-8"))
            c.commit()

        print("[CALL] analytics.refresh_unit_semantics_absorption_v11()")
        c.execute("CALL analytics.refresh_unit_semantics_absorption_v11()")
        c.commit()

        print("[CALL] analytics.refresh_stock_snapshot_actual_v11()")
        c.execute("CALL analytics.refresh_stock_snapshot_actual_v11()")
        c.commit()

    print("Unit semantics + absorption scope v1.1 instalado, refrescado y conciliado contra stock actual.")


if __name__ == "__main__":
    main()
