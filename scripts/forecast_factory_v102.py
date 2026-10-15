from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


DERIVATION_METHOD = "CUMULATIVE_TO_MONTHLY_INCREMENT_V102"


def fetch_dicts(cur, query, params=None):
    cur.execute(query, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def add_months(d: date, n: int) -> date:
    month0 = d.month - 1 + n
    y = d.year + month0 // 12
    m = month0 % 12 + 1
    return date(y, m, 1)


def month_start(v: Any) -> date:
    if isinstance(v, datetime):
        return date(v.year, v.month, 1)
    if isinstance(v, date):
        return date(v.year, v.month, 1)
    s = str(v).strip()
    if len(s) >= 7 and s[4] in "-/":
        return date(int(s[:4]), int(s[5:7]), 1)
    raise ValueError(f"Cannot normalize month value: {v!r}")


def as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí"}


def load_cfg(root: Path) -> dict:
    p = root / "config" / "forecast_factory_v102.json"
    return json.loads(p.read_text(encoding="utf-8"))


def install(root: Path, conn):
    p = (
        root / "sql" / "122_forecast_factory_v102"
        / "01_forecast_factory_v102.sql"
    )
    with conn.cursor() as cur:
        cur.execute(p.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def classify_evidence(source_class: str, issued_at: datetime, data_cutoff: date, target_period: date) -> str:
    source_class = (source_class or "").upper()

    if source_class == "BACKTEST":
        return "BACKTEST"

    # A monthly increment is strict prospective evidence if it was frozen
    # before that target month started and its data cutoff also predates it.
    if issued_at.date() < target_period and data_cutoff < target_period:
        return "PROSPECTIVE"

    return "SHADOW"


def lead_bucket(days: int) -> str:
    if days <= 0:
        return "IN_PERIOD_SHADOW"
    if days <= 30:
        return "LT_1_30D"
    if days <= 60:
        return "LT_31_60D"
    if days <= 90:
        return "LT_61_90D"
    return "LT_91D_PLUS"


def ensure_derived_model(cur, src: dict) -> int:
    model_name = f"{src['model_name']}__monthly_increment"
    model_version = f"{src['model_version']}__v102"
    model_family = f"DERIVED_MONTHLY_INCREMENT::{src['model_family']}"

    cur.execute(
        """
        INSERT INTO model_control.forecast_model_registry_v1(
            model_name, model_version, model_family,
            target_name, owner, lifecycle_status,
            repo_reference, code_sha, metadata
        )
        VALUES(
            %s,%s,%s,
            'sales_units','Medallio Forecast Factory',
            'DEVELOPMENT',
            'Forecast Factory v1.0.2 Monthly Increment Adapter',
            %s,%s
        )
        ON CONFLICT(model_name,model_version,target_name)
        DO UPDATE SET metadata=EXCLUDED.metadata
        RETURNING model_version_id
        """,
        (
            model_name,
            model_version,
            model_family,
            src["code_sha"],
            Jsonb({
                "derived_from_model_version_id": src["model_version_id"],
                "derived_from_model_name": src["model_name"],
                "derivation_method": DERIVATION_METHOD,
                "interval_semantics": "NOT_DERIVED_FROM_CUMULATIVE_BOUNDS",
            }),
        ),
    )
    return cur.fetchone()[0]


def ensure_derived_run(cur, source_run_id: int) -> int:
    cur.execute(
        """
        SELECT derived_run_id
        FROM model_control.forecast_derived_run_map_v102
        WHERE derivation_method=%s AND source_run_id=%s
        """,
        (DERIVATION_METHOD, source_run_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    src = fetch_dicts(
        cur,
        """
        SELECT
            r.*,
            mr.model_name,
            mr.model_version,
            mr.model_family
        FROM model_control.forecast_run_v1 r
        JOIN model_control.forecast_model_registry_v1 mr
          ON mr.model_version_id=r.model_version_id
        WHERE r.run_id=%s
        """,
        (source_run_id,),
    )[0]

    derived_model_version_id = ensure_derived_model(cur, src)

    cur.execute(
        """
        INSERT INTO model_control.forecast_run_v1(
            model_version_id,
            issued_at, data_cutoff_date,
            training_start_date, training_end_date,
            feature_version, dataset_snapshot_id,
            code_sha, run_status,
            run_parameters, environment_fingerprint, notes
        )
        VALUES(
            %s,
            %s,%s,
            %s,%s,
            %s,%s,
            %s,'ISSUED',
            %s,%s,%s
        )
        RETURNING run_id
        """,
        (
            derived_model_version_id,
            src["issued_at"], src["data_cutoff_date"],
            src["training_start_date"], src["training_end_date"],
            src["feature_version"], src["dataset_snapshot_id"],
            src["code_sha"],
            Jsonb({
                "derivation_method": DERIVATION_METHOD,
                "source_run_id": source_run_id,
                "source_model_version_id": src["model_version_id"],
            }),
            Jsonb(src.get("environment_fingerprint") or {}),
            f"Derived monthly increments from cumulative run_id={source_run_id}",
        ),
    )
    derived_run_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO model_control.forecast_derived_run_map_v102(
            derivation_method,
            source_run_id, derived_run_id,
            source_model_version_id, derived_model_version_id
        )
        VALUES(%s,%s,%s,%s,%s)
        """,
        (
            DERIVATION_METHOD,
            source_run_id,
            derived_run_id,
            src["model_version_id"],
            derived_model_version_id,
        ),
    )
    return derived_run_id


def adapt_monthly(conn):
    inserted = 0
    accepted = 0
    rejected = 0
    prospective = 0
    shadow = 0
    backtest = 0

    with conn.cursor() as cur:
        source_runs = fetch_dicts(
            cur,
            """
            SELECT DISTINCT run_id
            FROM analytics.v_pbi_forecast_factory_current_v101
            WHERE aggregation_semantics='CUMULATIVE_WINDOW'
            ORDER BY run_id
            """,
        )

        for rr in source_runs:
            source_run_id = rr["run_id"]
            derived_run_id = ensure_derived_run(cur, source_run_id)

            rows = fetch_dicts(
                cur,
                """
                SELECT
                    p.prediction_id,
                    p.run_id,
                    p.project_key,
                    p.target_name,
                    p.target_unit,
                    p.segment_key,
                    p.origin_period,
                    p.horizon_months,
                    p.prediction,
                    p.naive_method,
                    p.naive_prediction,
                    p.evidence_class,
                    p.scope_semantics,
                    p.source_system,
                    p.source_run_ref,
                    p.source_model_ref,

                    r.issued_at,
                    r.data_cutoff_date,
                    r.code_sha,

                    mr.model_name,
                    mr.model_version,
                    mr.model_family

                FROM analytics.forecast_prediction_v1 p
                JOIN model_control.forecast_run_v1 r
                  ON r.run_id=p.run_id
                JOIN model_control.forecast_model_registry_v1 mr
                  ON mr.model_version_id=r.model_version_id

                WHERE
                    p.run_id=%s
                    AND p.aggregation_semantics='CUMULATIVE_WINDOW'
                    AND p.derivation_method IS NULL

                ORDER BY
                    p.project_key,
                    p.segment_key,
                    p.horizon_months
                """,
                (source_run_id,),
            )

            by_key = {}
            for r in rows:
                key = (r["project_key"], r["segment_key"])
                by_key.setdefault(key, []).append(r)

            for (project, segment), group in by_key.items():
                by_h = {int(x["horizon_months"]): x for x in group}

                for h in sorted(by_h):
                    curr = by_h[h]
                    prev = by_h.get(h - 1) if h > 1 else None

                    target_period = add_months(curr["origin_period"], h)

                    if h > 1 and prev is None:
                        reason = "MISSING_PREVIOUS_CUMULATIVE_HORIZON"
                        cur.execute(
                            """
                            INSERT INTO model_control.forecast_adapter_audit_v102(
                                derivation_method,source_run_id,project_key,
                                source_horizon_months,source_prediction_id,
                                target_period,adapter_status,adapter_reason
                            )
                            VALUES(%s,%s,%s,%s,%s,%s,'REJECTED',%s)
                            ON CONFLICT(
                                derivation_method,source_run_id,project_key,source_horizon_months
                            ) DO UPDATE SET
                                adapter_status='REJECTED',
                                adapter_reason=EXCLUDED.adapter_reason,
                                audited_at=now()
                            """,
                            (
                                DERIVATION_METHOD, source_run_id, project,
                                h, curr["prediction_id"], target_period, reason
                            ),
                        )
                        rejected += 1
                        continue

                    pred_delta = (
                        curr["prediction"]
                        if h == 1
                        else curr["prediction"] - prev["prediction"]
                    )
                    naive_delta = (
                        curr["naive_prediction"]
                        if h == 1
                        else curr["naive_prediction"] - prev["naive_prediction"]
                    )

                    if pred_delta < 0 or naive_delta < 0:
                        reason = "NON_MONOTONIC_CUMULATIVE_PATH"
                        cur.execute(
                            """
                            INSERT INTO model_control.forecast_adapter_audit_v102(
                                derivation_method,source_run_id,project_key,
                                source_horizon_months,source_prediction_id,
                                source_previous_prediction_id,target_period,
                                prediction_delta,naive_delta,
                                adapter_status,adapter_reason
                            )
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'REJECTED',%s)
                            ON CONFLICT(
                                derivation_method,source_run_id,project_key,source_horizon_months
                            ) DO UPDATE SET
                                prediction_delta=EXCLUDED.prediction_delta,
                                naive_delta=EXCLUDED.naive_delta,
                                adapter_status='REJECTED',
                                adapter_reason=EXCLUDED.adapter_reason,
                                audited_at=now()
                            """,
                            (
                                DERIVATION_METHOD, source_run_id, project, h,
                                curr["prediction_id"],
                                prev["prediction_id"] if prev else None,
                                target_period,
                                pred_delta, naive_delta, reason,
                            ),
                        )
                        rejected += 1
                        continue

                    ev = classify_evidence(
                        curr["evidence_class"],
                        curr["issued_at"],
                        curr["data_cutoff_date"],
                        target_period,
                    )

                    lead_days = (target_period - curr["issued_at"].date()).days
                    issue_month = date(
                        curr["issued_at"].year,
                        curr["issued_at"].month,
                        1,
                    )
                    lead_months = (
                        (target_period.year - issue_month.year) * 12
                        + target_period.month - issue_month.month
                    )

                    cur.execute(
                        """
                        INSERT INTO analytics.forecast_prediction_v1(
                            run_id,
                            project_key,target_name,target_unit,segment_key,
                            forecast_for_period,horizon_months,

                            prediction,prediction_lower,prediction_upper,
                            interval_level,

                            naive_method,naive_prediction,
                            evidence_class,prediction_status,
                            maturity_date,issued_at_copy,data_cutoff_date_copy,

                            metadata,

                            origin_period,
                            forecast_window_start,forecast_window_end,
                            aggregation_semantics,scope_semantics,

                            source_system,source_run_ref,source_model_ref,

                            lead_time_days,lead_time_months,lead_time_bucket,
                            derivation_method,
                            source_prediction_id,
                            source_previous_prediction_id,
                            source_horizon_months
                        )
                        VALUES(
                            %s,
                            %s,'sales_units','units',%s,
                            %s,%s,

                            %s,NULL,NULL,
                            0.80,

                            %s,%s,
                            %s,'ISSUED',
                            %s,%s,%s,

                            %s,

                            %s,
                            %s,%s,
                            'PERIOD_VALUE','EXISTING_STOCK_NO_FUTURE_INFLOWS',

                            'FORECAST_FACTORY_V102',%s,%s,

                            %s,%s,%s,
                            %s,
                            %s,%s,%s
                        )
                        ON CONFLICT(
                            run_id,project_key,target_name,segment_key,
                            forecast_for_period,horizon_months
                        ) DO NOTHING
                        """,
                        (
                            derived_run_id,
                            project, segment,
                            target_period, h,

                            pred_delta,

                            curr["naive_method"], naive_delta,
                            ev,
                            add_months(target_period, 1),
                            curr["issued_at"],
                            curr["data_cutoff_date"],

                            Jsonb({
                                "source_evidence_class": curr["evidence_class"],
                                "interval_status": "INCUBATING_MONTHLY_RESIDUAL_CALIBRATION",
                                "source_cumulative_prediction": str(curr["prediction"]),
                                "source_previous_cumulative_prediction": (
                                    str(prev["prediction"]) if prev else None
                                ),
                                "monthly_increment_formula": (
                                    "H1" if h == 1 else f"H{h}-H{h-1}"
                                ),
                            }),

                            curr["origin_period"],
                            target_period, target_period,

                            str(source_run_id),
                            f"{curr['model_name']}:{curr['model_version']}",

                            lead_days, lead_months, lead_bucket(lead_days),
                            DERIVATION_METHOD,
                            curr["prediction_id"],
                            prev["prediction_id"] if prev else None,
                            h,
                        ),
                    )
                    inserted += cur.rowcount

                    cur.execute(
                        """
                        INSERT INTO model_control.forecast_adapter_audit_v102(
                            derivation_method,source_run_id,project_key,
                            source_horizon_months,source_prediction_id,
                            source_previous_prediction_id,target_period,
                            prediction_delta,naive_delta,
                            adapter_status,adapter_reason
                        )
                        VALUES(
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,
                            'ACCEPTED','MONTHLY_INCREMENT_DERIVED'
                        )
                        ON CONFLICT(
                            derivation_method,source_run_id,project_key,source_horizon_months
                        ) DO UPDATE SET
                            prediction_delta=EXCLUDED.prediction_delta,
                            naive_delta=EXCLUDED.naive_delta,
                            adapter_status='ACCEPTED',
                            adapter_reason='MONTHLY_INCREMENT_DERIVED',
                            audited_at=now()
                        """,
                        (
                            DERIVATION_METHOD, source_run_id, project, h,
                            curr["prediction_id"],
                            prev["prediction_id"] if prev else None,
                            target_period,
                            pred_delta, naive_delta,
                        ),
                    )

                    accepted += 1
                    prospective += ev == "PROSPECTIVE"
                    shadow += ev == "SHADOW"
                    backtest += ev == "BACKTEST"

    conn.commit()

    print(
        "[V1.0.2] monthly adapter | "
        f"inserted={inserted} accepted={accepted} rejected={rejected} | "
        f"prospective={prospective} shadow={shadow} backtest={backtest}"
    )


def relation_columns(cur, rel: str):
    schema, table = rel.split(".", 1)
    return fetch_dicts(
        cur,
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )


def resolve_column(available: set[str], candidates: list[str], override):
    if override:
        if override not in available:
            raise RuntimeError(
                f"Configured column {override!r} not found. Available={sorted(available)}"
            )
        return override
    for c in candidates:
        if c in available:
            return c
    return None


def get_source_mapping(cur, cfg):
    rel = cfg["actual_loader"]["source_relation"]
    cols = relation_columns(cur, rel)
    if not cols:
        raise RuntimeError(f"Source relation not found: {rel}")

    available = {r["column_name"] for r in cols}
    candidates = cfg["actual_loader"]["column_candidates"]
    overrides = cfg["actual_loader"]["column_overrides"]

    mapping = {
        role: resolve_column(
            available,
            candidates.get(role, []),
            overrides.get(role),
        )
        for role in candidates
    }

    for required in ("project", "period", "sales"):
        if not mapping[required]:
            raise RuntimeError(
                f"Could not detect {required!r} column in {rel}. "
                f"Available columns: {sorted(available)}. "
                f"Set config.forecast_factory_v102.json column_overrides.{required}."
            )

    print("[V1.0.2] actual source mapping:", mapping)
    return rel, mapping


def load_actuals(conn, root: Path):
    cfg = load_cfg(root)

    inserted = 0
    unchanged = 0
    revised = 0
    skipped_incomplete = 0

    with conn.cursor() as cur:
        rel, mp = get_source_mapping(cur, cfg)

        selected = [mp["project"], mp["period"], mp["sales"]]
        for optional in ("month_complete", "stock_initial", "stock_final"):
            if mp.get(optional):
                selected.append(mp[optional])

        query = sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(", ").join(sql.Identifier(c) for c in selected),
            sql.SQL(".").join(sql.Identifier(x) for x in rel.split(".")),
        )
        cur.execute(query)
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        cur.execute("SELECT current_date")
        today = cur.fetchone()[0]
        current_month = date(today.year, today.month, 1)

        # Keep monthly source snapshot in memory for scope calculation later.
        normalized = []

        for row in rows:
            project = str(row[mp["project"]]).strip()
            period = month_start(row[mp["period"]])
            sales = row[mp["sales"]]

            if project == "" or sales is None:
                continue

            if mp.get("month_complete"):
                complete = as_bool(row[mp["month_complete"]])
            else:
                complete = period < current_month

            if not complete:
                skipped_incomplete += 1
                continue

            actual_value = Decimal(str(sales))
            closed_at = add_months(period, 1)

            cur.execute(
                """
                SELECT actual_id,actual_value
                FROM analytics.forecast_actual_v1
                WHERE project_key=%s
                  AND target_name='sales_units'
                  AND segment_key='ALL'
                  AND actual_period=%s
                """,
                (project, period),
            )
            old = cur.fetchone()

            source_ref = f"{rel}:{project}:{period.isoformat()}"

            if old is None:
                cur.execute(
                    """
                    INSERT INTO analytics.forecast_actual_v1(
                        project_key,target_name,target_unit,segment_key,
                        actual_period,actual_value,
                        period_complete,period_closed_at,
                        source_relation,source_reference,source_snapshot_id
                    )
                    VALUES(
                        %s,'sales_units','units','ALL',
                        %s,%s,
                        true,%s,
                        %s,%s,NULL
                    )
                    """,
                    (
                        project, period, actual_value,
                        closed_at, rel, source_ref,
                    ),
                )
                inserted += 1
            else:
                actual_id, old_value = old
                if Decimal(str(old_value)) == actual_value:
                    unchanged += 1
                else:
                    cur.execute(
                        """
                        INSERT INTO analytics.forecast_actual_revision_v102(
                            actual_id,project_key,target_name,segment_key,
                            actual_period,old_actual_value,new_actual_value,
                            revision_reason,source_relation,source_reference
                        )
                        VALUES(
                            %s,%s,'sales_units','ALL',
                            %s,%s,%s,
                            'SOURCE_ACTUAL_REVISED',
                            %s,%s
                        )
                        """,
                        (
                            actual_id, project, period,
                            old_value, actual_value, rel, source_ref,
                        ),
                    )
                    cur.execute(
                        """
                        UPDATE analytics.forecast_actual_v1
                        SET actual_value=%s,
                            period_complete=true,
                            period_closed_at=%s,
                            source_relation=%s,
                            source_reference=%s,
                            loaded_at=now()
                        WHERE actual_id=%s
                        """,
                        (
                            actual_value, closed_at, rel, source_ref, actual_id
                        ),
                    )
                    revised += 1

            normalized.append({
                "project": project,
                "period": period,
                "sales": actual_value,
                "stock_initial": (
                    Decimal(str(row[mp["stock_initial"]]))
                    if mp.get("stock_initial") and row.get(mp["stock_initial"]) is not None
                    else None
                ),
                "stock_final": (
                    Decimal(str(row[mp["stock_final"]]))
                    if mp.get("stock_final") and row.get(mp["stock_final"]) is not None
                    else None
                ),
            })

        # -----------------------------------------------------------
        # Scope compatibility for every monthly derived prediction.
        # -----------------------------------------------------------
        by_project_period = {
            (r["project"], r["period"]): r
            for r in normalized
        }

        predictions = fetch_dicts(
            cur,
            """
            SELECT DISTINCT
                project_key,origin_period,forecast_for_period,scope_semantics
            FROM analytics.v_forecast_monthly_current_v102
            WHERE scope_semantics='EXISTING_STOCK_NO_FUTURE_INFLOWS'
            ORDER BY project_key,origin_period,forecast_for_period
            """,
        )

        tolerance = Decimal(str(
            cfg["scope_policy"]["inflow_tolerance_units"]
        ))

        compatible_n = 0
        blocked_n = 0

        for p in predictions:
            project = p["project_key"]
            origin = p["origin_period"]
            target = p["forecast_for_period"]

            months = []
            cursor = add_months(origin, 1)
            while cursor <= target:
                months.append(cursor)
                cursor = add_months(cursor, 1)

            src_rows = [
                by_project_period.get((project, m))
                for m in months
            ]

            complete_rows = [r for r in src_rows if r is not None]
            months_checked = len(months)
            months_complete = len(complete_rows)

            if months_complete < months_checked:
                status = "INCOMPLETE_WINDOW"
                compatible = False
                inflow = None
                note = (
                    f"Only {months_complete}/{months_checked} complete actual months available."
                )

            elif not mp.get("stock_initial") or not mp.get("stock_final"):
                status = "INSUFFICIENT_STOCK_FLOW_EVIDENCE"
                compatible = False
                inflow = None
                note = (
                    "Actual sales exist, but source lacks both stock_initial and stock_final; "
                    "existing-stock scope cannot be certified."
                )

            elif any(
                r["stock_initial"] is None or r["stock_final"] is None
                for r in complete_rows
            ):
                status = "INSUFFICIENT_STOCK_FLOW_EVIDENCE"
                compatible = False
                inflow = None
                note = "At least one month lacks stock flow fields."

            else:
                inflows = []
                for r in complete_rows:
                    implied = r["stock_final"] - r["stock_initial"] + r["sales"]
                    inflows.append(max(implied, Decimal("0")))

                inflow = sum(inflows, Decimal("0"))
                compatible = inflow <= tolerance

                status = (
                    "COMPATIBLE"
                    if compatible
                    else "INCOMPATIBLE_INFLOW"
                )
                note = (
                    f"Cumulative implied inflow={inflow}; "
                    f"tolerance={tolerance}."
                )

            cur.execute(
                """
                INSERT INTO analytics.forecast_scope_compatibility_v102(
                    project_key,origin_period,target_period,scope_semantics,
                    compatible_scope,compatibility_status,
                    cumulative_implied_inflow,
                    months_checked,months_complete,
                    source_relation,evidence_note,calculated_at
                )
                VALUES(
                    %s,%s,%s,%s,
                    %s,%s,%s,
                    %s,%s,%s,%s,now()
                )
                ON CONFLICT(
                    project_key,origin_period,target_period,scope_semantics
                )
                DO UPDATE SET
                    compatible_scope=EXCLUDED.compatible_scope,
                    compatibility_status=EXCLUDED.compatibility_status,
                    cumulative_implied_inflow=EXCLUDED.cumulative_implied_inflow,
                    months_checked=EXCLUDED.months_checked,
                    months_complete=EXCLUDED.months_complete,
                    source_relation=EXCLUDED.source_relation,
                    evidence_note=EXCLUDED.evidence_note,
                    calculated_at=now()
                """,
                (
                    project, origin, target, p["scope_semantics"],
                    compatible, status, inflow,
                    months_checked, months_complete,
                    rel, note,
                ),
            )

            compatible_n += int(compatible)
            blocked_n += int(not compatible)

    conn.commit()

    print(
        "[V1.0.2] actual loader | "
        f"inserted={inserted} unchanged={unchanged} revised={revised} "
        f"skipped_incomplete={skipped_incomplete}"
    )
    print(
        "[V1.0.2] scope compatibility | "
        f"compatible={compatible_n} blocked_or_incubating={blocked_n}"
    )


def status(conn):
    with conn.cursor() as cur:
        adapter = fetch_dicts(
            cur,
            """
            SELECT adapter_status,count(*) AS n
            FROM model_control.forecast_adapter_audit_v102
            GROUP BY adapter_status
            ORDER BY adapter_status
            """,
        )

        preds = fetch_dicts(
            cur,
            """
            SELECT
                evidence_class,
                lead_time_bucket,
                count(*) AS n
            FROM analytics.v_forecast_monthly_current_v102
            GROUP BY evidence_class,lead_time_bucket
            ORDER BY evidence_class,lead_time_bucket
            """,
        )

        maturity = fetch_dicts(
            cur,
            """
            SELECT maturity_status,count(*) AS n
            FROM analytics.v_forecast_monthly_maturity_clock_v102
            GROUP BY maturity_status
            ORDER BY maturity_status
            """,
        )

        clocks = fetch_dicts(
            cur,
            """
            SELECT
                issuance_clock_status,
                count(*) AS project_model_runs,
                min(next_maturity_date) AS next_maturity
            FROM analytics.v_forecast_issuance_clock_v102
            GROUP BY issuance_clock_status
            ORDER BY issuance_clock_status
            """,
        )

        gates = fetch_dicts(
            cur,
            """
            SELECT
                overall_gate_status,
                count(*) AS cells
            FROM analytics.v_forecast_lead_time_defendability_v102
            GROUP BY overall_gate_status
            ORDER BY overall_gate_status
            """,
        )

        actuals = fetch_dicts(
            cur,
            """
            SELECT count(*) AS n, max(actual_period) AS latest
            FROM analytics.forecast_actual_v1
            WHERE target_name='sales_units'
            """
        )[0]

        scope = fetch_dicts(
            cur,
            """
            SELECT compatibility_status,count(*) AS n
            FROM analytics.forecast_scope_compatibility_v102
            GROUP BY compatibility_status
            ORDER BY compatibility_status
            """,
        )

    print("[V1.0.2] Adapter")
    if not adapter:
        print("  no adapter audit yet")
    for r in adapter:
        print(f"  {r['adapter_status']}={r['n']}")

    print("[V1.0.2] Monthly predictions by evidence/lead time")
    if not preds:
        print("  no monthly predictions yet")
    for r in preds:
        print(
            f"  {r['evidence_class']} | {r['lead_time_bucket']} | n={r['n']}"
        )

    print(
        "[V1.0.2] Actuals | "
        f"rows={actuals['n']} latest={actuals['latest']}"
    )

    print("[V1.0.2] Scope compatibility")
    if not scope:
        print("  no scope checks yet")
    for r in scope:
        print(f"  {r['compatibility_status']}={r['n']}")

    print("[V1.0.2] Maturity")
    if not maturity:
        print("  no maturity rows yet")
    for r in maturity:
        print(f"  {r['maturity_status']}={r['n']}")

    print("[V1.0.2] Issuance clock")
    if not clocks:
        print("  no issuance clock yet")
    for r in clocks:
        print(
            f"  {r['issuance_clock_status']} | "
            f"runs={r['project_model_runs']} | "
            f"next_maturity={r['next_maturity']}"
        )

    print("[V1.0.2] Lead-time defendability")
    if not gates:
        print("  no mature performance cells yet")
    for r in gates:
        print(f"  {r['overall_gate_status']}={r['cells']}")


def run_all(conn, root: Path):
    install(root, conn)
    adapt_monthly(conn)
    load_actuals(conn, root)
    status(conn)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        nargs="?",
        choices=[
            "install",
            "adapt-monthly",
            "load-actuals",
            "status",
            "run-all",
        ],
        default="status",
    )
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install(root, conn)
            print("[V1.0.2] schema installed.")
        elif args.command == "adapt-monthly":
            adapt_monthly(conn)
        elif args.command == "load-actuals":
            load_actuals(conn, root)
        elif args.command == "run-all":
            run_all(conn, root)
        else:
            status(conn)


if __name__ == "__main__":
    main()
