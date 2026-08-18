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
CATEGORY_HINTS = (
    "tipo", "estado", "resultado", "canal", "medio", "origen", "nombre",
    "accion", "actividad", "asunto", "motivo", "categoria", "subtipo",
)
DATE_COLUMNS = ("fecha_programada", "fecha_creacion", "fecha_actualizacion", "_etl_loaded_at")
TEMPORAL_TYPES = {"date", "timestamp without time zone", "timestamp with time zone"}


def _fetch(conn, query: str | sql.Composed, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else fallback
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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


def _linkage_decomposition(conn, columns: dict[str, str]) -> dict[str, Any]:
    has_proforma = "codigo_proforma" in columns
    has_doc = "documento_cliente" in columns
    has_client_id = "cliente_id" in columns
    if not has_proforma:
        return {"status": "BLOCKED_NO_CODIGO_PROFORMA"}

    doc_expr = "nullif(btrim(i.documento_cliente::text), '')" if has_doc else "null::text"
    client_expr = "nullif(btrim(i.cliente_id::text), '')" if has_client_id else "null::text"
    query = f"""
    with base as (
        select
            nullif(btrim(i.codigo_proforma::text), '') as codigo_proforma,
            {doc_expr} as documento_cliente,
            {client_expr} as cliente_id
        from raw_cygnus.interacciones i
    ), core_proformas as (
        select distinct nullif(btrim(codigo_proforma::text), '') as codigo_proforma
        from core.fact_ciclo_comercial_unidad
        where nullif(btrim(codigo_proforma::text), '') is not null
    ), outcome_clients as (
        select
            nullif(btrim(documento_cliente::text), '') as documento_cliente,
            count(distinct separation_id)::bigint as lifecycle_count,
            count(distinct codigo_proforma)::bigint as proforma_count
        from decision_intelligence.v_separation_fall_training_outcome
        where nullif(btrim(documento_cliente::text), '') is not null
        group by nullif(btrim(documento_cliente::text), '')
    ), direct as (
        select
            count(*) filter (where b.codigo_proforma is not null)::bigint as rows_with_proforma,
            count(*) filter (where b.codigo_proforma is null)::bigint as rows_without_proforma,
            count(distinct b.codigo_proforma) filter (where b.codigo_proforma is not null)::bigint as distinct_proformas,
            count(*) filter (where b.codigo_proforma is not null and cp.codigo_proforma is not null)::bigint as rows_with_proforma_matching_core,
            count(*) filter (where b.codigo_proforma is not null and cp.codigo_proforma is null)::bigint as rows_with_proforma_unmatched_core,
            count(distinct b.codigo_proforma) filter (where b.codigo_proforma is not null and cp.codigo_proforma is not null)::bigint as distinct_proformas_matching_core,
            count(distinct b.codigo_proforma) filter (where b.codigo_proforma is not null and cp.codigo_proforma is null)::bigint as distinct_proformas_unmatched_core,
            count(*) filter (where b.documento_cliente is not null)::bigint as rows_with_documento_cliente,
            count(*) filter (where b.codigo_proforma is null and b.documento_cliente is not null)::bigint as rows_without_proforma_with_documento_cliente,
            count(*) filter (where b.cliente_id is not null)::bigint as rows_with_cliente_id,
            count(*)::bigint as total_rows
        from base b
        left join core_proformas cp using (codigo_proforma)
    ), client_link as (
        select
            count(*) filter (
                where b.codigo_proforma is null
                  and b.documento_cliente is not null
                  and oc.documento_cliente is not null
            )::bigint as no_proforma_rows_matching_training_client,
            count(*) filter (
                where b.codigo_proforma is null
                  and b.documento_cliente is not null
                  and oc.lifecycle_count = 1
            )::bigint as no_proforma_rows_unambiguous_single_lifecycle_client,
            count(*) filter (
                where b.codigo_proforma is null
                  and b.documento_cliente is not null
                  and oc.lifecycle_count > 1
            )::bigint as no_proforma_rows_ambiguous_multi_lifecycle_client,
            count(distinct b.documento_cliente) filter (
                where b.codigo_proforma is null
                  and b.documento_cliente is not null
                  and oc.documento_cliente is not null
            )::bigint as distinct_no_proforma_clients_matching_training,
            count(distinct b.documento_cliente) filter (
                where b.codigo_proforma is null
                  and b.documento_cliente is not null
                  and oc.lifecycle_count > 1
            )::bigint as distinct_ambiguous_multi_lifecycle_clients
        from base b
        left join outcome_clients oc using (documento_cliente)
    ), core_coverage as (
        select
            count(*)::bigint as core_proformas_total,
            count(*) filter (
                where exists (
                    select 1 from base b where b.codigo_proforma = cp.codigo_proforma
                )
            )::bigint as core_proformas_with_direct_interaction
        from core_proformas cp
    )
    select * from direct cross join client_link cross join core_coverage
    """
    out = _fetch(conn, query)[0]
    total = int(out.get("total_rows") or 0)
    with_pf = int(out.get("rows_with_proforma") or 0)
    core_total = int(out.get("core_proformas_total") or 0)
    core_with = int(out.get("core_proformas_with_direct_interaction") or 0)
    out["row_direct_proforma_rate"] = float(with_pf / total) if total else None
    out["direct_proforma_core_match_rate"] = (
        float((out.get("rows_with_proforma_matching_core") or 0) / with_pf) if with_pf else None
    )
    out["core_proforma_direct_interaction_coverage"] = float(core_with / core_total) if core_total else None
    out["status"] = "PROFILED_NOT_CERTIFIED"
    return out


def _duplicate_samples(conn, columns: dict[str, str], limit: int = 100) -> list[dict[str, Any]]:
    if "id" not in columns:
        return []
    selected = [c for c in [
        "id", "codigo_proforma", "documento_cliente", "cliente_id",
        "fecha_programada", "fecha_creacion", "fecha_actualizacion",
        "tipo", "estado", "resultado", "canal", "medio", "nombre",
    ] if c in columns]
    select_sql = sql.SQL(", ").join(sql.Identifier(c) for c in selected)
    q = sql.SQL(
        """
        with dup as (
            select id
            from {t}
            where id is not null
            group by id
            having count(*) > 1
            order by count(*) desc, id
            limit {limit}
        )
        select {cols}
        from {t} i
        join dup d using (id)
        order by i.id, i.fecha_creacion nulls last, i.fecha_actualizacion nulls last
        """
    ).format(
        t=sql.Identifier(SCHEMA, TABLE),
        cols=select_sql,
        limit=sql.Literal(limit),
    )
    return _fetch(conn, q)


def _candidate_categories(conn, columns: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for col in columns:
        lower = col.lower()
        if not any(h in lower for h in CATEGORY_HINTS):
            continue
        q_stats = sql.SQL(
            "select count({c})::bigint as non_null_rows, count(distinct {c})::bigint as distinct_count from {t}"
        ).format(c=sql.Identifier(col), t=sql.Identifier(SCHEMA, TABLE))
        stat = _fetch(conn, q_stats)[0]
        distinct_count = int(stat["distinct_count"] or 0)
        if distinct_count == 0 or distinct_count > 250:
            continue
        q_top = sql.SQL(
            """
            select {name}::text as column_name, {c}::text as value, count(*)::bigint as rows
            from {t}
            where {c} is not null
            group by {c}
            order by count(*) desc, {c}::text
            limit 25
            """
        ).format(name=sql.Literal(col), c=sql.Identifier(col), t=sql.Identifier(SCHEMA, TABLE))
        for r in _fetch(conn, q_top):
            rows.append({
                "column_name": r["column_name"],
                "value": r["value"],
                "rows": r["rows"],
                "column_non_null_rows": stat["non_null_rows"],
                "column_distinct_count": distinct_count,
            })
    return rows


def _timestamp_pairs(conn, columns: dict[str, str]) -> list[dict[str, Any]]:
    temporal = [c for c in DATE_COLUMNS if columns.get(c) in TEMPORAL_TYPES]
    rows: list[dict[str, Any]] = []
    for left, right in [
        ("fecha_creacion", "fecha_programada"),
        ("fecha_creacion", "fecha_actualizacion"),
        ("fecha_programada", "fecha_actualizacion"),
    ]:
        if left not in temporal or right not in temporal:
            continue
        q = sql.SQL(
            """
            with x as (
                select
                    {l} as l,
                    {r} as r,
                    extract(epoch from ({r} - {l})) / 3600.0 as delta_hours
                from {t}
                where {l} is not null and {r} is not null
            )
            select
                {left_name}::text as left_timestamp,
                {right_name}::text as right_timestamp,
                count(*)::bigint as both_non_null_rows,
                count(*) filter (where l = r)::bigint as equal_rows,
                count(*) filter (where l < r)::bigint as left_before_right_rows,
                count(*) filter (where l > r)::bigint as left_after_right_rows,
                percentile_cont(0.5) within group (order by delta_hours) as median_right_minus_left_hours,
                percentile_cont(0.9) within group (order by delta_hours) as p90_right_minus_left_hours
            from x
            """
        ).format(
            l=sql.Identifier(left),
            r=sql.Identifier(right),
            t=sql.Identifier(SCHEMA, TABLE),
            left_name=sql.Literal(left),
            right_name=sql.Literal(right),
        )
        rows.extend(_fetch(conn, q))
    return rows


def main() -> int:
    settings = load_settings()
    out = settings.project_root / "reports" / "interaction_contract_stage3"
    out.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        columns = _columns(conn)
        linkage = _linkage_decomposition(conn, columns)
        duplicate_samples = _duplicate_samples(conn, columns)
        category_values = _candidate_categories(conn, columns)
        timestamp_pairs = _timestamp_pairs(conn, columns)

    _write_csv(out / "linkage_decomposition.csv", [linkage], list(linkage.keys()) or ["status"])
    _write_csv(out / "duplicate_id_samples.csv", duplicate_samples, ["id"])
    _write_csv(out / "category_top_values.csv", category_values, ["column_name", "value", "rows"])
    _write_csv(out / "timestamp_pair_semantics.csv", timestamp_pairs, ["left_timestamp"])

    summary = {
        "status": "STAGE3_PROFILED_NOT_CERTIFIED",
        "source": f"{SCHEMA}.{TABLE}",
        "linkage_decomposition": linkage,
        "interpretation_guards": [
            "Stage2 interaction_rows_unmatched_to_core_proforma included the NULL codigo_proforma bucket and must not be read as 792k bad proforma codes; stage3 separates rows_without_proforma from genuinely unmatched non-null proformas.",
            "One direct codigo_proforma row per proforma strongly suggests codigo_proforma is populated only for a subset/event family; do not treat direct-proforma rows as the complete interaction history without category/timestamp review.",
            "Customer-level linkage by documento_cliente is discovery only. Multi-lifecycle customers require temporal attribution after event-time certification; never fan one customer interaction out to every proforma.",
            "Duplicate id groups block id-only interaction identity certification until duplicate samples explain whether a composite key is required.",
        ],
        "event_time_status": "NOT_CERTIFIED",
        "next_decision": (
            "Review category_top_values + timestamp_pair_semantics + duplicate_id_samples. "
            "If fecha_creacion is certified as event occurrence/record time and customer-level event attribution is safe, "
            "build a canonical interaction_event view before point-in-time features."
        ),
        "outputs": [
            "linkage_decomposition.csv",
            "duplicate_id_samples.csv",
            "category_top_values.csv",
            "timestamp_pair_semantics.csv",
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
