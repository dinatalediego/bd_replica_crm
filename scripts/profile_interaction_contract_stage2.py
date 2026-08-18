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
DATE_COLUMNS = ["fecha_programada", "fecha_creacion", "fecha_actualizacion", "_etl_loaded_at"]
NATIVE_TEMPORAL_TYPES = {
    "date",
    "timestamp without time zone",
    "timestamp with time zone",
}


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else fallback
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fetch(conn, query: str | sql.Composed, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def _columns(conn) -> dict[str, str]:
    rows = _fetch(
        conn,
        """
        select column_name, data_type
        from information_schema.columns
        where table_schema = %s and table_name = %s
        order by ordinal_position
        """,
        (SCHEMA, TABLE),
    )
    return {str(r["column_name"]): str(r["data_type"]) for r in rows}


def _timestamp_profile(conn, column: str, data_type: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "column_name": column,
        "data_type": data_type,
        "native_temporal": data_type in NATIVE_TEMPORAL_TYPES,
        "non_null_rows": None,
        "null_rows": None,
        "non_null_rate": None,
        "min_value": None,
        "max_value": None,
        "future_rows_gt_now_plus_1d": None,
        "pre_2000_rows": None,
    }
    if data_type not in NATIVE_TEMPORAL_TYPES:
        return row

    q = sql.SQL(
        """
        select
            count({c})::bigint as non_null_rows,
            count(*) filter (where {c} is null)::bigint as null_rows,
            count({c})::numeric / nullif(count(*), 0) as non_null_rate,
            min({c}) as min_value,
            max({c}) as max_value,
            count(*) filter (where {c} > current_timestamp + interval '1 day')::bigint
                as future_rows_gt_now_plus_1d,
            count(*) filter (where {c} < timestamp '2000-01-01')::bigint as pre_2000_rows
        from {t}
        """
    ).format(c=sql.Identifier(column), t=sql.Identifier(SCHEMA, TABLE))
    return {**row, **_fetch(conn, q)[0]}


def _timestamp_relationship(
    conn,
    left: str,
    right: str,
    columns: dict[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "left_timestamp": left,
        "right_timestamp": right,
        "comparable": False,
        "both_non_null_rows": None,
        "left_le_right_rows": None,
        "left_gt_right_rows": None,
        "median_right_minus_left_days": None,
        "p90_right_minus_left_days": None,
    }
    if columns.get(left) not in NATIVE_TEMPORAL_TYPES or columns.get(right) not in NATIVE_TEMPORAL_TYPES:
        return out

    l = sql.Identifier(left)
    r = sql.Identifier(right)
    q = sql.SQL(
        """
        with d as (
            select
                {l}, {r},
                extract(epoch from ({r} - {l})) / 86400.0 as delta_days
            from {t}
            where {l} is not null and {r} is not null
        )
        select
            count(*)::bigint as both_non_null_rows,
            count(*) filter (where {l} <= {r})::bigint as left_le_right_rows,
            count(*) filter (where {l} > {r})::bigint as left_gt_right_rows,
            percentile_cont(0.5) within group (order by delta_days) as median_right_minus_left_days,
            percentile_cont(0.9) within group (order by delta_days) as p90_right_minus_left_days
        from d
        """
    ).format(l=l, r=r, t=sql.Identifier(SCHEMA, TABLE))
    return {**out, "comparable": True, **_fetch(conn, q)[0]}


def _identity_health(conn, columns: dict[str, str]) -> dict[str, Any]:
    if "id" not in columns:
        return {"status": "BLOCKED_NO_ID_COLUMN"}
    rows = _fetch(
        conn,
        """
        with dup_id as (
            select id, count(*) as n
            from raw_cygnus.interacciones
            where id is not null
            group by id
            having count(*) > 1
        ), dup_id_proforma as (
            select id, nullif(btrim(codigo_proforma::text), '') as codigo_proforma, count(*) as n
            from raw_cygnus.interacciones
            where id is not null
            group by id, nullif(btrim(codigo_proforma::text), '')
            having count(*) > 1
        )
        select
            (select count(*) from raw_cygnus.interacciones)::bigint as row_count,
            (select count(*) from raw_cygnus.interacciones where id is null)::bigint as null_id_rows,
            (select count(distinct id) from raw_cygnus.interacciones)::bigint as distinct_ids,
            (select count(*) from dup_id)::bigint as duplicate_id_groups,
            coalesce((select sum(n - 1) from dup_id), 0)::bigint as duplicate_id_excess_rows,
            (select count(*) from dup_id_proforma)::bigint as duplicate_id_proforma_groups
        """,
    )
    return {"status": "PROFILED_NOT_CERTIFIED", **rows[0]}


def _linkage_health(conn, columns: dict[str, str]) -> dict[str, Any]:
    if "codigo_proforma" not in columns:
        return {"status": "BLOCKED_NO_CODIGO_PROFORMA"}
    rows = _fetch(
        conn,
        """
        with interactions as (
            select
                nullif(btrim(codigo_proforma::text), '') as codigo_proforma,
                count(*)::bigint as interaction_rows
            from raw_cygnus.interacciones
            group by nullif(btrim(codigo_proforma::text), '')
        ), core_proformas as (
            select distinct nullif(btrim(codigo_proforma::text), '') as codigo_proforma
            from core.fact_ciclo_comercial_unidad
            where nullif(btrim(codigo_proforma::text), '') is not null
        ), training_map as (
            select
                nullif(btrim(codigo_proforma::text), '') as codigo_proforma,
                count(distinct separation_id)::bigint as lifecycle_count
            from decision_intelligence.v_separation_fall_training_outcome
            where nullif(btrim(codigo_proforma::text), '') is not null
            group by nullif(btrim(codigo_proforma::text), '')
        )
        select
            (select coalesce(sum(interaction_rows), 0) from interactions where codigo_proforma is not null)::bigint
                as interaction_rows_with_proforma,
            (select count(*) from interactions where codigo_proforma is not null)::bigint
                as distinct_interaction_proformas,
            coalesce(sum(i.interaction_rows) filter (where c.codigo_proforma is not null), 0)::bigint
                as interaction_rows_matching_core_proforma,
            coalesce(sum(i.interaction_rows) filter (where c.codigo_proforma is null), 0)::bigint
                as interaction_rows_unmatched_to_core_proforma,
            count(*) filter (where i.codigo_proforma is not null and c.codigo_proforma is not null)::bigint
                as distinct_interaction_proformas_matching_core,
            count(*) filter (where i.codigo_proforma is not null and c.codigo_proforma is null)::bigint
                as distinct_interaction_proformas_unmatched_core,
            count(*) filter (where i.codigo_proforma is not null and tm.lifecycle_count > 1)::bigint
                as interaction_proformas_with_multiple_training_lifecycles
        from interactions i
        left join core_proformas c using (codigo_proforma)
        left join training_map tm using (codigo_proforma)
        """,
    )
    out = rows[0]
    denom = int(out.get("interaction_rows_with_proforma") or 0)
    out["interaction_row_core_match_rate"] = (
        float(out.get("interaction_rows_matching_core_proforma") or 0) / denom if denom else None
    )
    out["status"] = "PROFILED_NOT_CERTIFIED"
    return out


def _proforma_distribution(conn) -> dict[str, Any]:
    rows = _fetch(
        conn,
        """
        with counts as (
            select codigo_proforma::text as codigo_proforma, count(*)::bigint as n
            from raw_cygnus.interacciones
            where nullif(btrim(codigo_proforma::text), '') is not null
            group by codigo_proforma::text
        )
        select
            count(*)::bigint as proformas,
            avg(n)::numeric as avg_interactions_per_proforma,
            percentile_cont(0.5) within group (order by n) as p50_interactions_per_proforma,
            percentile_cont(0.9) within group (order by n) as p90_interactions_per_proforma,
            percentile_cont(0.99) within group (order by n) as p99_interactions_per_proforma,
            max(n)::bigint as max_interactions_per_proforma
        from counts
        """,
    )
    return rows[0]


def _year_coverage(conn, column: str, data_type: str) -> list[dict[str, Any]]:
    if data_type not in NATIVE_TEMPORAL_TYPES:
        return []
    q = sql.SQL(
        """
        select
            {name}::text as timestamp_candidate,
            extract(year from {c})::int as event_year,
            count(*)::bigint as rows,
            count(distinct nullif(btrim(codigo_proforma::text), ''))::bigint as distinct_proformas
        from {t}
        where {c} is not null
        group by extract(year from {c})
        order by event_year
        """
    ).format(
        name=sql.Literal(column),
        c=sql.Identifier(column),
        t=sql.Identifier(SCHEMA, TABLE),
    )
    return _fetch(conn, q)


def main() -> int:
    settings = load_settings()
    out = settings.project_root / "reports" / "interaction_contract_stage2"
    out.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        columns = _columns(conn)
        identity = _identity_health(conn, columns)
        linkage = _linkage_health(conn, columns)
        distribution = _proforma_distribution(conn)

        timestamp_profiles = [
            _timestamp_profile(conn, c, columns[c])
            for c in DATE_COLUMNS
            if c in columns
        ]
        relationships = [
            _timestamp_relationship(conn, a, b, columns)
            for a, b in [
                ("fecha_creacion", "fecha_programada"),
                ("fecha_creacion", "fecha_actualizacion"),
                ("fecha_actualizacion", "_etl_loaded_at"),
                ("fecha_creacion", "_etl_loaded_at"),
            ]
            if a in columns and b in columns
        ]
        year_rows: list[dict[str, Any]] = []
        for c in DATE_COLUMNS:
            if c in columns:
                year_rows.extend(_year_coverage(conn, c, columns[c]))

    _write_csv(out / "timestamp_profiles.csv", timestamp_profiles, ["column_name"])
    _write_csv(out / "timestamp_relationships.csv", relationships, ["left_timestamp"])
    _write_csv(out / "timestamp_year_coverage.csv", year_rows, ["timestamp_candidate", "event_year"])
    _write_csv(out / "identity_health.csv", [identity], list(identity.keys()) or ["status"])
    _write_csv(out / "proforma_linkage_health.csv", [linkage], list(linkage.keys()) or ["status"])
    _write_csv(out / "proforma_interaction_distribution.csv", [distribution], list(distribution.keys()))

    temporal_native = {
        r["column_name"]: bool(r["native_temporal"])
        for r in timestamp_profiles
    }
    summary = {
        "status": "STAGE2_PROFILED_NOT_CERTIFIED",
        "source": f"{SCHEMA}.{TABLE}",
        "identity_health": identity,
        "proforma_linkage_health": linkage,
        "proforma_interaction_distribution": distribution,
        "timestamp_candidates_native_temporal": temporal_native,
        "event_time_decision": "REVIEW_REQUIRED_DO_NOT_AUTO_CERTIFY",
        "event_time_semantic_question": (
            "Choose the timestamp that means the business interaction happened. "
            "fecha_actualizacion and _etl_loaded_at are not eligible merely because they are complete."
        ),
        "linkage_policy_candidate": (
            "Prefer direct codigo_proforma attribution. Aggregate interaction events by codigo_proforma "
            "before joining to lifecycle snapshots to prevent unit-grain row multiplication."
        ),
        "next_gate": (
            "Review timestamp semantics + identity duplicates + direct proforma coverage. "
            "Only after approval build as-of features with interaction_event_at <= snapshot_at."
        ),
        "outputs": [
            "timestamp_profiles.csv",
            "timestamp_relationships.csv",
            "timestamp_year_coverage.csv",
            "identity_health.csv",
            "proforma_linkage_health.csv",
            "proforma_interaction_distribution.csv",
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
