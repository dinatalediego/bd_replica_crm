from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


SCHEMA = "raw_cygnus"
TABLE = "interacciones"

DATE_HINTS = ("fecha", "date", "time", "created", "updated", "inicio", "fin")
KEY_HINTS = ("proforma", "cliente", "documento", "codigo", "id")
CATEGORY_HINTS = ("tipo", "estado", "resultado", "canal", "medio", "origen", "nombre")
TEMPORAL_TYPES = {"date", "timestamp without time zone", "timestamp with time zone"}


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else fallback
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _columns(conn) -> list[dict[str, Any]]:
    query = """
        select
            ordinal_position,
            column_name,
            data_type,
            is_nullable
        from information_schema.columns
        where table_schema = %s
          and table_name = %s
        order by ordinal_position
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (SCHEMA, TABLE))
        return [dict(r) for r in cur.fetchall()]


def _scalar(conn, query: sql.Composed) -> Any:
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()[0]


def _profile_column(conn, column: str, data_type: str, total_rows: int) -> dict[str, Any]:
    ident = sql.Identifier(column)
    table = sql.Identifier(SCHEMA, TABLE)
    q = sql.SQL(
        "select count({c}), count(distinct {c}) from {t}"
    ).format(c=ident, t=table)
    with conn.cursor() as cur:
        cur.execute(q)
        non_null, distinct_count = cur.fetchone()

    result: dict[str, Any] = {
        "column_name": column,
        "data_type": data_type,
        "total_rows": total_rows,
        "non_null_rows": int(non_null),
        "null_rows": int(total_rows - non_null),
        "non_null_rate": round(float(non_null / total_rows), 6) if total_rows else None,
        "distinct_count": int(distinct_count),
    }

    if data_type in TEMPORAL_TYPES:
        q2 = sql.SQL("select min({c}), max({c}) from {t}").format(c=ident, t=table)
        with conn.cursor() as cur:
            cur.execute(q2)
            min_value, max_value = cur.fetchone()
        result["min_value"] = min_value
        result["max_value"] = max_value
    else:
        result["min_value"] = None
        result["max_value"] = None
    return result


def _top_values(conn, column: str, limit: int = 15) -> list[dict[str, Any]]:
    q = sql.SQL(
        """
        select {c}::text as value, count(*)::bigint as rows
        from {t}
        where {c} is not null
        group by {c}
        order by count(*) desc, {c}::text
        limit {limit}
        """
    ).format(
        c=sql.Identifier(column),
        t=sql.Identifier(SCHEMA, TABLE),
        limit=sql.Literal(limit),
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(q)
        return [{"column_name": column, **dict(r)} for r in cur.fetchall()]


def main() -> int:
    settings = load_settings()
    out = settings.project_root / "reports" / "interaction_contract_discovery"
    out.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        columns = _columns(conn)
        if not columns:
            raise RuntimeError(f"No existe {SCHEMA}.{TABLE} o no tiene columnas visibles.")

        total_rows = int(
            _scalar(
                conn,
                sql.SQL("select count(*) from {t}").format(t=sql.Identifier(SCHEMA, TABLE)),
            )
        )

        profiles = [
            _profile_column(conn, str(c["column_name"]), str(c["data_type"]), total_rows)
            for c in columns
        ]

        date_candidates = [
            p for p in profiles
            if p["data_type"] in TEMPORAL_TYPES
            or any(h in p["column_name"].lower() for h in DATE_HINTS)
        ]
        key_candidates = [
            p for p in profiles
            if any(h in p["column_name"].lower() for h in KEY_HINTS)
        ]
        category_candidates = [
            p for p in profiles
            if any(h in p["column_name"].lower() for h in CATEGORY_HINTS)
            and p["distinct_count"] <= 100
        ]

        top_values: list[dict[str, Any]] = []
        for p in category_candidates[:12]:
            top_values.extend(_top_values(conn, str(p["column_name"])))

    _write_csv(out / "columns.csv", columns, ["ordinal_position", "column_name", "data_type", "is_nullable"])
    _write_csv(out / "column_profiles.csv", profiles, ["column_name"])
    _write_csv(out / "date_candidates.csv", date_candidates, ["column_name"])
    _write_csv(out / "key_candidates.csv", key_candidates, ["column_name"])
    _write_csv(out / "category_top_values.csv", top_values, ["column_name", "value", "rows"])

    names = {str(c["column_name"]).lower() for c in columns}
    summary = {
        "status": "DISCOVERY_ONLY_NOT_CERTIFIED",
        "source": f"{SCHEMA}.{TABLE}",
        "row_count": total_rows,
        "column_count": len(columns),
        "date_candidates": [p["column_name"] for p in date_candidates],
        "key_candidates": [p["column_name"] for p in key_candidates],
        "direct_codigo_proforma_available": "codigo_proforma" in names,
        "direct_documento_cliente_available": "documento_cliente" in names,
        "certification_gates": [
            "choose source event timestamp; ETL/update timestamp is not accepted as behavioral event time",
            "choose entity join key and prove row-level linkage to separation/proforma without many-to-many inflation",
            "prove interaction identity/deduplication key",
            "prove historical coverage and freshness by period",
            "build as-of features using only events <= snapshot_at",
            "re-run mature out-of-time benchmark before any promotion",
        ],
        "candidate_features_after_certification": [
            "days_since_last_interaction",
            "interaction_count_7d",
            "interaction_count_14d",
            "interaction_count_30d",
            "active_days_with_interaction_30d",
            "interaction_channel_diversity_30d",
            "interaction_velocity_7d_vs_30d",
        ],
        "outputs": [
            "columns.csv",
            "column_profiles.csv",
            "date_candidates.csv",
            "key_candidates.csv",
            "category_top_values.csv",
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
