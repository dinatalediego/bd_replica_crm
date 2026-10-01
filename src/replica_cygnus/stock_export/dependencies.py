from __future__ import annotations

from pathlib import Path

from .service import ROOT, _connect

UNIDADES_VIEW_SQL = ROOT / "sql" / "40_unidades_multifuente" / "01_v_unidades_fuentes.sql"


def ensure_unidades_view() -> None:
    """Garantiza la dependencia mínima core.v_unidades_fuentes.

    No instala toda la capa 40_unidades_multifuente: solo la vista canónica
    necesaria para el exportador de stock. Es idempotente y reutiliza la
    conexión PostgreSQL/Medallio del módulo.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('core.v_unidades_fuentes')")
            exists = cur.fetchone()[0] is not None
            if exists:
                return

            if not UNIDADES_VIEW_SQL.exists():
                raise RuntimeError(
                    "Falta core.v_unidades_fuentes y no se encontró "
                    f"{UNIDADES_VIEW_SQL.relative_to(ROOT)} para instalarla."
                )

            print("[preflight] core.v_unidades_fuentes no existe; instalando dependencia mínima...")
            cur.execute(UNIDADES_VIEW_SQL.read_text(encoding="utf-8"))
        conn.commit()

    print("[preflight] OK: core.v_unidades_fuentes disponible")
