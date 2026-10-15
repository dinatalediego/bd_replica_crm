from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


HISTORICAL_SOURCES = [
    "analytics.commercial_forecast_predictions",
    "analytics.commercial_forecast_backtest",
    "features.commercial_forecast_snapshots",
]

CURRENT_SOURCE = "analytics.v_commercial_forecast_current"

ALIASES = {
    "run_id": ["run_id", "model_run_id", "id_run", "forecast_run_id"],
    "project": ["project", "project_key", "codigo_proyecto", "proyecto", "project_code"],
    "origin": [
        "origin", "origin_period", "forecast_origin", "periodo_origen",
        "fecha_origen", "fecha_corte", "cutoff_date", "as_of_date"
    ],
    "target": [
        "target_period", "forecast_period", "periodo_objetivo", "target_month",
        "mes_objetivo", "periodo_forecast"
    ],
    "horizon": ["horizon", "horizonte", "horizon_months", "horizonte_meses"],
    "prediction": [
        "prediction", "prediccion", "forecast", "y_pred",
        "predicted_sales", "ventas_predichas", "forecast_units"
    ],
    "created_at": [
        "created_at", "issued_at", "generated_at", "forecast_created_at",
        "captured_at", "run_created_at"
    ],
    "selected": ["is_selected", "selected", "seleccionado", "is_champion"],
    "model_name": ["model_name", "modelo", "model", "algorithm", "metodo"],
    "model_version": ["model_version", "version", "version_modelo", "model_id"],
    "stock": ["stock", "stock_at_origin", "stock_base", "stock_inicial"],
    "target_sales": ["target_sales", "meta_ventas", "target", "goal"],
    "shortfall": ["expected_shortfall", "shortfall", "forecast_shortfall"],
}


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def safe_relation(rel: str) -> str:
    parts = rel.split(".")
    if len(parts) != 2:
        raise ValueError(f"Relación inválida: {rel}")
    return ".".join(qident(x) for x in parts)


def relation_exists(cur, rel: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def relation_columns(cur, rel: str) -> list[str]:
    schema, table = rel.split(".", 1)
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    return [r[0] for r in cur.fetchall()]


def pick(columns: list[str], key: str) -> str | None:
    lookup = {c.lower(): c for c in columns}
    for alias in ALIASES[key]:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    return None


def first_of_month(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return date(value.year, value.month, 1)

    if isinstance(value, date):
        return date(value.year, value.month, 1)

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%Y/%m"):
        try:
            dt = datetime.strptime(text[:10] if "%d" in fmt else text[:7], fmt)
            return date(dt.year, dt.month, 1)
        except Exception:
            pass

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return date(dt.year, dt.month, 1)
    except Exception:
        return None


def as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        d = first_of_month(text)
        return datetime(d.year, d.month, 1, tzinfo=timezone.utc) if d else None


def add_months(d: date, months: int) -> date:
    idx = (d.year * 12 + (d.month - 1)) + months
    return date(idx // 12, idx % 12 + 1, 1)


def sub_months(d: date, months: int) -> date:
    return add_months(d, -months)


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except Exception:
        return None


def as_num(value: Any):
    if value is None or value == "":
        return None
    try:
        x = float(value)
        return None if math.isnan(x) else x
    except Exception:
        return None


def as_bool(value: Any, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "si", "sí", "selected", "champion"}:
        return True
    if text in {"0", "false", "f", "no", "n"}:
        return False
    return default


def canonical_hash(payload: dict) -> str:
    keys = [
        "run_id", "project_key", "origin_period", "target_period",
        "horizon", "prediction", "model_name", "model_version"
    ]
    raw = json.dumps(
        {k: payload.get(k) for k in keys},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()



def prospective_signature(payload: dict) -> str:
    """Signature of the business forecast itself, excluding issue/run timestamps."""
    raw = json.dumps(
        {
            "project_key": payload.get("project_key"),
            "target_period": payload.get("target_period"),
            "horizon": payload.get("horizon"),
            "prediction": payload.get("prediction"),
            "model_name": payload.get("model_name"),
            "model_version": payload.get("model_version"),
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _select_current_candidates(rows: list[dict], columns: list[str], source_relation: str):
    """
    Collapse the current forecast relation to at most one selected row per
    project×target×horizon. Ambiguous cells are not issued.
    """
    standardized = []
    skipped = 0
    reasons = {}
    selected_col = pick(columns, "selected")

    for row in rows:
        payload, reason = standardize_row(row, columns, source_relation, "PROSPECTIVE_CAPTURE")
        if payload is None:
            skipped += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue

        payload["source_created_at"] = (
            as_datetime(row.get(pick(columns, "created_at")))
            if pick(columns, "created_at")
            else None
        )
        payload["has_selection_flag"] = selected_col is not None
        standardized.append(payload)

    groups = {}
    for p in standardized:
        key = (p["project_key"], p["target_period"], p["horizon"])
        groups.setdefault(key, []).append(p)

    chosen = []
    ambiguous = 0
    for key, group in groups.items():
        selected = [p for p in group if p.get("is_selected") is True]
        if not selected:
            continue

        if len(selected) == 1:
            chosen.append(selected[0])
            continue

        # Multiple selected rows are only resolvable with explicit source timestamps.
        if all(p.get("source_created_at") is not None for p in selected):
            selected.sort(
                key=lambda p: (p.get("source_created_at"), p.get("model_version") or ""),
                reverse=True,
            )
            if (
                len(selected) == 1
                or selected[0].get("source_created_at")
                > selected[1].get("source_created_at")
            ):
                chosen.append(selected[0])
                continue

        ambiguous += 1

    return {
        "chosen": chosen,
        "source_rows": len(rows),
        "candidate_cells": len(groups),
        "ambiguous_cells": ambiguous,
        "skipped_rows": skipped,
        "skip_reasons": reasons,
    }


def capture_prospective_registry(
    conn,
    slot: str,
    *,
    dry_run: bool = False,
    capture_reason: str = "AMBASSADOR",
):
    """
    Freeze the current selected forecast into an immutable prospective registry.
    Unchanged forecasts are not duplicated; changed forecasts create a revision.
    """
    with conn.cursor() as cur:
        if not relation_exists(cur, "model_control.forecast_issue_registry"):
            return {"status": "SCHEMA_NOT_INSTALLED"}
        if not relation_exists(cur, CURRENT_SOURCE):
            return {"status": "CURRENT_SOURCE_MISSING", "source": CURRENT_SOURCE}

        columns = relation_columns(cur, CURRENT_SOURCE)
        rows = fetch_dicts(cur, f"SELECT * FROM {safe_relation(CURRENT_SOURCE)} LIMIT 50000")
        selection = _select_current_candidates(rows, columns, CURRENT_SOURCE)

        issued_at = datetime.now(timezone.utc)
        chosen = selection["chosen"]

        if dry_run:
            return {
                "status": "DRY_RUN_NOT_ISSUED",
                "source": CURRENT_SOURCE,
                **{k: v for k, v in selection.items() if k != "chosen"},
                "would_issue_candidates": len(chosen),
            }

        batch_id = f"fib_{uuid.uuid4().hex}"
        cur.execute(
            """
            INSERT INTO model_control.forecast_issue_batch(
                issue_batch_id, issued_at, slot, source_relation, capture_reason,
                source_rows, candidate_cells, ambiguous_cells, skipped_rows,
                capture_status, metadata
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN',%s::jsonb)
            """,
            (
                batch_id, issued_at, slot, CURRENT_SOURCE, capture_reason,
                selection["source_rows"], selection["candidate_cells"],
                selection["ambiguous_cells"], selection["skipped_rows"],
                json.dumps({"skip_reasons": selection["skip_reasons"]}, ensure_ascii=False),
            ),
        )

        inserted = 0
        unchanged = 0

        for p in chosen:
            sig = prospective_signature(p)

            cur.execute(
                """
                SELECT forecast_signature
                FROM model_control.forecast_issue_registry
                WHERE project_key = %s
                  AND target_period = %s
                  AND horizon = %s
                ORDER BY issued_at DESC, issue_id DESC
                LIMIT 1
                """,
                (p["project_key"], p["target_period"], p["horizon"]),
            )
            prev = cur.fetchone()
            if prev and prev[0] == sig:
                unchanged += 1
                continue

            issue_id = f"fi_{uuid.uuid4().hex}"
            issue_month = date(issued_at.year, issued_at.month, 1)
            source_payload = dict(p.get("raw_metadata") or {})
            source_payload.update({
                "captured_by": "Medallio Ambassador v2.8.3",
                "source_created_at": p.get("source_created_at"),
            })

            cur.execute(
                """
                INSERT INTO model_control.forecast_issue_registry(
                    issue_id, issue_batch_id, forecast_signature,
                    source_relation, source_run_id, slot,
                    issued_at, source_created_at, data_cutoff,
                    project_key, origin_period, target_period, horizon, prediction,
                    model_name, model_version,
                    stock_at_issue, target_sales, expected_shortfall,
                    issuance_evidence, immutable, source_payload
                )
                VALUES (
                    %s,%s,%s,
                    %s,%s,%s,
                    %s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,
                    %s,%s,%s,
                    'AMBASSADOR_CAPTURE',true,%s::jsonb
                )
                """,
                (
                    issue_id, batch_id, sig,
                    CURRENT_SOURCE, p.get("run_id"), slot,
                    issued_at, p.get("source_created_at"), issue_month,
                    p["project_key"], p.get("origin_period"), p["target_period"],
                    p["horizon"], p["prediction"],
                    p.get("model_name"), p.get("model_version"),
                    p.get("stock_at_origin"), p.get("target_sales"),
                    p.get("expected_shortfall"),
                    json.dumps(source_payload, ensure_ascii=False, default=str),
                ),
            )
            inserted += 1

        cur.execute(
            "SELECT model_control.populate_naive_benchmarks_v283(%s)",
            (batch_id,),
        )
        benchmark_rows = int(cur.fetchone()[0] or 0)

        cur.execute(
            """
            UPDATE model_control.forecast_issue_batch
               SET inserted_rows = %s,
                   unchanged_rows = %s,
                   capture_status = 'COMPLETE',
                   completed_at = now()
             WHERE issue_batch_id = %s
            """,
            (inserted, unchanged, batch_id),
        )

    conn.commit()
    return {
        "status": "OK",
        "issue_batch_id": batch_id,
        "issued_at": issued_at.isoformat(),
        "source": CURRENT_SOURCE,
        "source_rows": selection["source_rows"],
        "candidate_cells": selection["candidate_cells"],
        "inserted": inserted,
        "unchanged": unchanged,
        "ambiguous_cells": selection["ambiguous_cells"],
        "skipped_rows": selection["skipped_rows"],
        "benchmark_rows": benchmark_rows,
    }


def refresh_maturity_v283(conn):
    with conn.cursor() as cur:
        if not relation_exists(cur, "analytics.v_forecast_maturity_clock_v283"):
            return {"status": "SCHEMA_NOT_INSTALLED", "new_matured": 0}
        cur.execute("SELECT analytics.refresh_forecast_maturity_v283()")
        n = int(cur.fetchone()[0] or 0)
    conn.commit()
    return {"status": "OK", "new_matured": n}


def standardize_row(row: dict, columns: list[str], source_relation: str, capture_mode: str):
    m = {key: pick(columns, key) for key in ALIASES}

    project = row.get(m["project"]) if m["project"] else None
    horizon = as_int(row.get(m["horizon"])) if m["horizon"] else None
    prediction = as_num(row.get(m["prediction"])) if m["prediction"] else None

    origin = first_of_month(row.get(m["origin"])) if m["origin"] else None
    target = first_of_month(row.get(m["target"])) if m["target"] else None

    if horizon is None or horizon < 1:
        return None, "missing_horizon"
    if project is None or str(project).strip() == "":
        return None, "missing_project"
    if prediction is None:
        return None, "missing_prediction"

    if target is None and origin is not None:
        target = add_months(origin, horizon)
    elif origin is None and target is not None:
        origin = sub_months(target, horizon)

    if target is None:
        return None, "missing_target"

    created_at = as_datetime(row.get(m["created_at"])) if m["created_at"] else None
    if created_at is not None:
        issued_at = created_at
        issuance_evidence = "SOURCE_CREATED_AT"
    elif origin is not None:
        issued_at = datetime(origin.year, origin.month, 1, tzinfo=timezone.utc)
        issuance_evidence = "DERIVED_FROM_ORIGIN"
    else:
        issued_at = None
        issuance_evidence = "UNKNOWN"

    leakage_safe = bool(
        issued_at is not None
        and issued_at.date() < target
    )

    payload = {
        "source_relation": source_relation,
        "capture_mode": capture_mode,
        "run_id": str(row.get(m["run_id"])) if m["run_id"] and row.get(m["run_id"]) is not None else None,
        "project_key": str(project).strip(),
        "origin_period": origin,
        "target_period": target,
        "horizon": horizon,
        "prediction": prediction,
        "issued_at": issued_at,
        "issuance_evidence": issuance_evidence,
        "leakage_safe": leakage_safe,
        "is_selected": as_bool(row.get(m["selected"]), default=True) if m["selected"] else True,
        "model_name": str(row.get(m["model_name"])) if m["model_name"] and row.get(m["model_name"]) is not None else None,
        "model_version": str(row.get(m["model_version"])) if m["model_version"] and row.get(m["model_version"]) is not None else None,
        "stock_at_origin": as_num(row.get(m["stock"])) if m["stock"] else None,
        "target_sales": as_num(row.get(m["target_sales"])) if m["target_sales"] else None,
        "expected_shortfall": as_num(row.get(m["shortfall"])) if m["shortfall"] else None,
    }
    payload["source_hash"] = canonical_hash(payload)

    payload["raw_metadata"] = {
        "source_relation": source_relation,
        "capture_mode": capture_mode,
        "mapped_columns": {k: v for k, v in m.items() if v},
    }

    return payload, None


def fetch_dicts(cur, sql: str, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def insert_snapshot(cur, p: dict):
    cur.execute(
        """
        INSERT INTO model_control.forecast_prediction_snapshot(
            source_hash, source_relation, capture_mode,
            run_id, project_key, origin_period, target_period, horizon, prediction,
            issued_at, issuance_evidence, leakage_safe,
            is_selected, model_name, model_version,
            stock_at_origin, target_sales, expected_shortfall,
            raw_metadata
        )
        VALUES (
            %s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,
            %s::jsonb
        )
        ON CONFLICT (source_hash) DO NOTHING
        """,
        (
            p["source_hash"], p["source_relation"], p["capture_mode"],
            p["run_id"], p["project_key"], p["origin_period"], p["target_period"],
            p["horizon"], p["prediction"],
            p["issued_at"], p["issuance_evidence"], p["leakage_safe"],
            p["is_selected"], p["model_name"], p["model_version"],
            p["stock_at_origin"], p["target_sales"], p["expected_shortfall"],
            json.dumps(p["raw_metadata"], ensure_ascii=False, default=str),
        ),
    )
    return cur.rowcount


def ingest_relation(cur, rel: str, mode: str, limit: int = 200000):
    if not relation_exists(cur, rel):
        return {
            "source": rel,
            "status": "MISSING",
            "read_rows": 0,
            "inserted": 0,
            "skipped": 0,
        }

    columns = relation_columns(cur, rel)
    required = {
        "project": pick(columns, "project"),
        "horizon": pick(columns, "horizon"),
        "prediction": pick(columns, "prediction"),
    }

    if not all(required.values()):
        return {
            "source": rel,
            "status": "UNMAPPED",
            "columns": columns,
            "required_mapping": required,
            "read_rows": 0,
            "inserted": 0,
            "skipped": 0,
        }

    rows = fetch_dicts(
        cur,
        f"SELECT * FROM {safe_relation(rel)} LIMIT {int(limit)}"
    )

    inserted = 0
    skipped = 0
    reasons = {}

    for row in rows:
        payload, reason = standardize_row(row, columns, rel, mode)
        if payload is None:
            skipped += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue

        inserted += insert_snapshot(cur, payload)

    return {
        "source": rel,
        "status": "OK",
        "read_rows": len(rows),
        "inserted": inserted,
        "skipped": skipped,
        "skip_reasons": reasons,
    }


def apply_schema(root: Path, conn):
    sql_path = root / "sql" / "103_forecast_predictive_gate" / "01_predictive_gate.sql"
    if not sql_path.exists():
        raise FileNotFoundError(sql_path)
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def capture_current(conn):
    with conn.cursor() as cur:
        result = ingest_relation(cur, CURRENT_SOURCE, "CURRENT_CAPTURE", limit=50000)
    conn.commit()
    return result


def backfill_history(conn):
    results = []
    with conn.cursor() as cur:
        for rel in HISTORICAL_SOURCES:
            results.append(ingest_relation(cur, rel, "HISTORICAL_BACKFILL"))
    conn.commit()
    return results


def predictive_status(conn):
    with conn.cursor() as cur:
        has_v283 = relation_exists(cur, "analytics.v_forecast_predictive_gate_v283")
        has_legacy = relation_exists(cur, "analytics.v_forecast_predictive_gate")
        if not has_v283 and not has_legacy:
            return {"status": "SCHEMA_NOT_INSTALLED"}

        if has_v283:
            rows = fetch_dicts(
                cur,
                "SELECT * FROM analytics.v_forecast_predictive_gate_v283"
            )
            gate = rows[0] if rows else {}
            perf = fetch_dicts(
                cur,
                """
                SELECT *
                FROM analytics.v_forecast_performance_v283
                ORDER BY
                    CASE defense_status
                        WHEN 'DEFENSIBLE' THEN 1
                        WHEN 'WATCH' THEN 2
                        ELSE 3
                    END,
                    wape_pct NULLS LAST,
                    mature_pairs DESC,
                    project_key,
                    horizon
                """
            )
            defensible = fetch_dicts(
                cur,
                "SELECT * FROM analytics.v_forecast_defensible_v283 LIMIT 25"
            )
        else:
            rows = fetch_dicts(
                cur,
                "SELECT * FROM analytics.v_forecast_predictive_gate"
            )
            gate = rows[0] if rows else {}
            perf = fetch_dicts(
                cur,
                """
                SELECT *
                FROM analytics.v_forecast_performance_by_project_horizon
                ORDER BY
                    CASE defense_status
                        WHEN 'DEFENSIBLE' THEN 1
                        WHEN 'WATCH' THEN 2
                        ELSE 3
                    END,
                    wape_pct NULLS LAST,
                    mature_pairs DESC,
                    project_key,
                    horizon
                """
            )
            defensible = fetch_dicts(
                cur,
                "SELECT * FROM analytics.v_forecast_defensible LIMIT 25"
            )

        source_diagnostic = []
        evidence_audit = []
        if relation_exists(cur, "analytics.v_forecast_source_diagnostic"):
            source_diagnostic = fetch_dicts(
                cur,
                """
                SELECT *
                FROM analytics.v_forecast_source_diagnostic
                ORDER BY matched_rows DESC
                """
            )
        if relation_exists(cur, "analytics.v_forecast_snapshot_cell_audit"):
            evidence_audit = fetch_dicts(
                cur,
                """
                SELECT *
                FROM analytics.v_forecast_snapshot_cell_audit
                ORDER BY snapshot_rows DESC
                """
            )

        factory_summary = {}
        maturity_clock = []
        issue_registry = []
        benchmark_snapshot = []

        if has_v283:
            fs = fetch_dicts(cur, "SELECT * FROM analytics.v_predictive_evidence_factory_v283")
            factory_summary = fs[0] if fs else {}
            maturity_clock = fetch_dicts(
                cur,
                """
                SELECT *
                FROM analytics.v_forecast_maturity_clock_v283
                ORDER BY
                    CASE maturity_status
                        WHEN 'OVERDUE_NO_ACTUAL' THEN 1
                        WHEN 'INCUBATING' THEN 2
                        ELSE 3
                    END,
                    expected_maturity_date,
                    project_key,
                    horizon
                LIMIT 500
                """
            )
            issue_registry = fetch_dicts(
                cur,
                """
                SELECT
                    issue_id, issue_batch_id, project_key, origin_period,
                    target_period, horizon, prediction, issued_at, slot,
                    model_name, model_version, source_run_id,
                    stock_at_issue, target_sales, expected_shortfall
                FROM model_control.forecast_issue_registry
                ORDER BY issued_at DESC, project_key, horizon
                LIMIT 1000
                """
            )
            benchmark_snapshot = fetch_dicts(
                cur,
                """
                SELECT
                    b.issue_id, i.project_key, i.target_period, i.horizon,
                    b.benchmark_method, b.benchmark_prediction,
                    b.benchmark_history_rows, b.benchmark_cutoff,
                    b.primary_benchmark
                FROM model_control.forecast_naive_benchmark_snapshot b
                JOIN model_control.forecast_issue_registry i
                  ON i.issue_id = b.issue_id
                ORDER BY i.issued_at DESC, i.project_key, i.horizon,
                         b.primary_benchmark DESC, b.benchmark_method
                LIMIT 3000
                """
            )

        if relation_exists(cur, "model_control.forecast_prediction_snapshot"):
            cur.execute(
                "SELECT count(*) FROM model_control.forecast_prediction_snapshot"
            )
            snapshots = int(cur.fetchone()[0])
        else:
            snapshots = 0

    return {
        "status": "OK",
        "snapshot_rows": snapshots,
        "gate": gate,
        "performance": perf,
        "defensible": defensible,
        "source_diagnostic": source_diagnostic,
        "evidence_audit": evidence_audit,
        "factory_summary": factory_summary,
        "maturity_clock": maturity_clock,
        "issue_registry": issue_registry,
        "benchmark_snapshot": benchmark_snapshot,
        "gate_version": "v2.8.3" if has_v283 else "v2.8.2",
    }


def export_artifacts(root: Path, status: dict):
    out = root / "artifacts" / "medallio_ceo_briefing"
    out.mkdir(parents=True, exist_ok=True)

    gate = status.get("gate") or {}
    perf = status.get("performance") or []
    defensible = status.get("defensible") or []
    source_diagnostic = status.get("source_diagnostic") or []
    evidence_audit = status.get("evidence_audit") or []
    factory_summary = status.get("factory_summary") or {}
    maturity_clock = status.get("maturity_clock") or []
    issue_registry = status.get("issue_registry") or []
    benchmark_snapshot = status.get("benchmark_snapshot") or []

    (out / "forecast_predictive_gate.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "snapshot_rows": status.get("snapshot_rows"),
                "gate": gate,
                "gate_version": status.get("gate_version"),
                "factory_summary": factory_summary,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    def write_csv(name, rows):
        path = out / name
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    write_csv("forecast_performance_project_horizon.csv", perf)
    write_csv("forecast_defensible.csv", defensible)
    write_csv("forecast_source_diagnostic.csv", source_diagnostic)
    write_csv("forecast_evidence_audit.csv", evidence_audit)
    write_csv("forecast_issue_registry_current.csv", issue_registry)
    write_csv("forecast_maturity_clock.csv", maturity_clock)
    write_csv("forecast_naive_benchmarks.csv", benchmark_snapshot)

    (out / "forecast_factory_summary.json").write_text(
        json.dumps(
            factory_summary,
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    # CEO chart: honest when there is not enough mature evidence.
    try:
        import matplotlib.pyplot as plt

        chart = out / "05_ceo_defensible_forecasts.png"
        top = [r for r in perf if r.get("mature_pairs")][:10]

        fig, ax = plt.subplots(figsize=(12, 6))
        if top:
            labels = [
                f"{r.get('project_key')} · H{r.get('horizon')} · n={r.get('mature_pairs')}"
                for r in top
            ]
            values = [
                float(r.get("wape_pct")) if r.get("wape_pct") is not None else 0.0
                for r in top
            ]
            ax.barh(labels[::-1], values[::-1])
            ax.axvline(25, linestyle="--")
            ax.set_xlabel("WAPE maduro (%)")
            ax.set_title("Predicciones que ya podemos defender — proyecto × horizonte")
            for i, (value, row) in enumerate(zip(values[::-1], top[::-1])):
                status_label = row.get("defense_status") or "?"
                ax.text(value + 0.5, i, status_label, va="center")
        else:
            ax.axis("off")
            ax.text(
                0.5, 0.58,
                "Todavía no hay pares forecast → actual maduros",
                ha="center", va="center", fontsize=18,
                transform=ax.transAxes,
            )
            ax.text(
                0.5, 0.43,
                "Medallio no promoverá precisión predictiva hasta acumular outcomes completos.",
                ha="center", va="center", fontsize=12,
                transform=ax.transAxes,
            )
        fig.tight_layout()
        fig.savefig(chart, dpi=160)
        plt.close(fig)
    except Exception:
        pass



    # Evidence factory chart: useful before the first outcome matures.
    try:
        import matplotlib.pyplot as plt

        chart = out / "06_predictive_evidence_factory.png"
        labels = ["Emitidos", "Incubando", "Evaluados", "Defendibles"]
        values = [
            float(factory_summary.get("issued_total") or 0),
            float(factory_summary.get("incubating") or 0),
            float(factory_summary.get("evaluated") or 0),
            float(factory_summary.get("defensible_cells") or 0),
        ]
        fig, ax = plt.subplots(figsize=(10, 5.5))
        ax.bar(labels, values)
        ax.set_title("Predictive Evidence Factory — Medallio v2.8.3")
        ax.set_ylabel("Registros / celdas")
        for i, v in enumerate(values):
            ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom")
        fig.tight_layout()
        fig.savefig(chart, dpi=160)
        plt.close(fig)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["install", "backfill", "capture", "prospective", "maturity", "status", "all"],
        nargs="?",
        default="status",
    )
    args = parser.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command in {"install", "all"}:
            apply_schema(root, conn)
            print("[V2.8] schema: OK")

        if args.command in {"backfill", "all"}:
            results = backfill_history(conn)
            print("[V2.8] backfill:")
            for r in results:
                print(
                    f"  {r['source']}: status={r['status']} "
                    f"read={r.get('read_rows', 0)} inserted={r.get('inserted', 0)} "
                    f"skipped={r.get('skipped', 0)}"
                )

        if args.command in {"capture", "all"}:
            result = capture_current(conn)
            print(
                f"[V2.8] legacy current capture: status={result['status']} "
                f"read={result.get('read_rows', 0)} inserted={result.get('inserted', 0)}"
            )

        if args.command in {"prospective", "all"}:
            result = capture_prospective_registry(
                conn,
                slot="manual",
                dry_run=False,
                capture_reason="CLI",
            )
            print(
                "[V2.8.3] prospective issue: "
                f"status={result.get('status')} | "
                f"source_rows={result.get('source_rows')} | "
                f"candidates={result.get('candidate_cells')} | "
                f"inserted={result.get('inserted')} | "
                f"unchanged={result.get('unchanged')} | "
                f"ambiguous={result.get('ambiguous_cells')}"
            )

        if args.command in {"maturity", "prospective", "all"}:
            maturity = refresh_maturity_v283(conn)
            print(
                "[V2.8.3] maturity refresh: "
                f"status={maturity.get('status')} | "
                f"new_matured={maturity.get('new_matured')}"
            )

        status = predictive_status(conn)

    if status.get("status") == "OK":
        export_artifacts(root, status)
        gate = status.get("gate") or {}
        print(
            "[PREDICTIVE_GATE] "
            f"status={gate.get('gate_status')} | "
            f"pairs={gate.get('mature_pairs')} | "
            f"projects={gate.get('projects_with_mature')} | "
            f"defensible_cells={gate.get('defensible_cells')} | "
            f"WAPE={gate.get('global_wape_pct')} | "
            f"Bias={gate.get('global_bias_pct')}"
        )
        print(f"[PREDICTIVE_GATE] {gate.get('gate_reason')}")
        print(f"[PREDICTIVE_GATE] snapshots={status.get('snapshot_rows')}")

        factory = status.get("factory_summary") or {}
        if factory:
            print(
                "[PREDICTIVE_FACTORY] "
                f"issued={factory.get('issued_total')} | "
                f"active={factory.get('active_forecast_cells')} | "
                f"incubating={factory.get('incubating')} | "
                f"evaluated={factory.get('evaluated')} | "
                f"next_maturity={factory.get('next_maturity_date')} | "
                f"naive_WAPE={factory.get('naive_wape_pct')} | "
                f"skill={factory.get('skill_vs_naive_pct')}"
            )

        source_diag = status.get("source_diagnostic") or []
        if source_diag:
            print("[PREDICTIVE_AUDIT] source diagnostics:")
            for r in source_diag[:10]:
                print(
                    f"  {r.get('source_relation')} | "
                    f"class={r.get('evidence_class')} | "
                    f"rows={r.get('matched_rows')} | "
                    f"cells={r.get('distinct_cells')} | "
                    f"ratio={r.get('prediction_to_actual_ratio')} | "
                    f"WAPE={r.get('diagnostic_wape_pct')} | "
                    f"Bias={r.get('diagnostic_bias_pct')}"
                )
    else:
        print("[PREDICTIVE_GATE] schema not installed.")


if __name__ == "__main__":
    main()
