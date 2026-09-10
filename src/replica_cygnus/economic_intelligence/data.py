from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from replica_cygnus.stock_export.service import _connect
from replica_cygnus.monthly_stock_export.service import install_monthly_stock_sql


ROOT = Path(__file__).resolve().parents[3]
SQL_PATH = ROOT / "sql" / "70_economic_intelligence" / "00_feature_views.sql"


def _query_df(sql: str, params: list[object] | None = None) -> pd.DataFrame:
    with _connect() as conn:
        with conn.cursor() as cur:
            if params is None:
                cur.execute(sql)
            else:
                cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def install_feature_mart() -> None:
    """Install reporting views only; does not rebuild or truncate historical facts."""
    install_monthly_stock_sql()
    sql = SQL_PATH.read_text(encoding="utf-8")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def load_monthly_panel(projects: Iterable[str] | None = None) -> pd.DataFrame:
    params: list[object] = []
    where = ""
    if projects:
        names = [str(x).strip() for x in projects if str(x).strip()]
        if names:
            where = "WHERE proyecto IN (" + ",".join(["%s"] * len(names)) + ")"
            params.extend(names)

    df = _query_df(
        f"""
        SELECT *
        FROM analytics.v_econ_project_monthly_features
        {where}
        ORDER BY proyecto, periodo_mes
        """,
        params or None,
    )
    if not df.empty:
        df["periodo_mes"] = pd.to_datetime(df["periodo_mes"])
        if "fecha_inicio_comercial" in df:
            df["fecha_inicio_comercial"] = pd.to_datetime(df["fecha_inicio_comercial"], errors="coerce")
    return df


def load_macro_inputs() -> pd.DataFrame:
    df = _query_df("SELECT * FROM analytics.econ_macro_monthly ORDER BY periodo_mes")
    if not df.empty:
        df["periodo_mes"] = pd.to_datetime(df["periodo_mes"])
    return df
