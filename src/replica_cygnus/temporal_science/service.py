from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from psycopg.types.json import Jsonb

from .micro import fit_micro_horizon
from .profiling import population_stability_index, profile_numeric, profile_series, recommend_models

LIMA = ZoneInfo("America/Lima")
MACRO_VARIABLES = [
    "ventas_mes", "stock_inicial", "stock_final", "absorcion_mes",
    "ventas_por_30_dias_unidad", "unidades_revision",
]
MICRO_VARIABLES = [
    "dormitorios", "area_total", "area_relativa", "precio_m2", "precio_relativo",
    "mes_vida", "leads_4w", "proformas_4w", "interacciones_4w", "visitas_4w",
]


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def ensure_schema(conn, root: Path) -> None:
    sql = (root / "sql/102_temporal_science/01_control_plane.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql, prepare=False)
    conn.commit()


def _frame(cur, query: str, params=None) -> pd.DataFrame:
    cur.execute(query, params or ())
    columns = [c.name for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=columns)


def read_macro(conn) -> tuple[pd.DataFrame, pd.DataFrame]:
    with conn.cursor() as cur:
        projects = _frame(cur, "SELECT * FROM forecasting_macro.v_project_month ORDER BY codigo_proyecto, periodo_mes")
        portfolio = _frame(cur, "SELECT * FROM forecasting_macro.v_portfolio_month ORDER BY periodo_mes")
    return projects, portfolio


def read_micro(conn) -> pd.DataFrame:
    with conn.cursor() as cur:
        return _frame(cur, "SELECT * FROM forecasting_micro.v_unit_training ORDER BY fecha_corte, codigo_proyecto, codigo_unidad, horizonte_dias")


def _source_fingerprint(projects: pd.DataFrame, micro: pd.DataFrame) -> str:
    macro_cols = [c for c in ["codigo_proyecto", "periodo_mes", "ventas_mes", "stock_inicial", "stock_final", "unidades_revision"] if c in projects]
    digest = hashlib.sha256(projects[macro_cols].to_csv(index=False).encode("utf-8"))
    if len(micro):
        summary = micro.groupby(["evidencia", "horizonte_dias"], dropna=False).agg(
            rows=("codigo_unidad", "size"),
            first_cut=("fecha_corte", "min"),
            last_cut=("fecha_corte", "max"),
            mature=("maduro", "sum"),
        ).reset_index()
        digest.update(summary.to_csv(index=False).encode("utf-8"))
    return digest.hexdigest()


def _insert_registry(cur, *, series_key: str, scope: str, entity_level: str, entity_id: str,
                     target: str, frequency: str, source: str, hierarchy: str | None, metadata: dict) -> None:
    cur.execute(
        """INSERT INTO forecasting_control.series_registry
        (series_key,scope,entity_level,entity_id,target_name,frequency,source_relation,hierarchy_path,metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(series_key) DO UPDATE SET
          active=true, target_name=excluded.target_name, frequency=excluded.frequency,
          source_relation=excluded.source_relation, hierarchy_path=excluded.hierarchy_path,
          metadata=excluded.metadata, updated_at=clock_timestamp()""",
        (series_key, scope, entity_level, entity_id, target, frequency, source, hierarchy, Jsonb(json_safe(metadata))),
    )


def _insert_profile(cur, run_id: str, series_key: str, variable: str, role: str, profile: dict, metadata=None) -> None:
    fields = [
        "observed_from", "observed_to", "observations", "missing_periods", "null_rate", "zero_rate",
        "mean_value", "std_value", "min_value", "q05", "q25", "median", "q75", "q95", "max_value",
        "skewness", "kurtosis", "acf1", "acf12", "trend_slope", "seasonal_strength", "adi", "cv2",
        "demand_pattern", "adf_pvalue", "kpss_pvalue",
    ]
    values = [profile.get(f) for f in fields]
    cur.execute(
        f"""INSERT INTO forecasting_control.variable_profile
        (run_id,series_key,variable_name,variable_role,{','.join(fields)},metadata)
        VALUES (%s,%s,%s,%s,{','.join(['%s'] * len(fields))},%s)""",
        (run_id, series_key, variable, role, *values, Jsonb(json_safe(metadata or {}))),
    )


def _insert_recommendations(cur, run_id: str, series_key: str, recommendations: list[dict]) -> None:
    for rec in recommendations:
        cur.execute(
            """INSERT INTO forecasting_control.model_suitability
            (run_id,series_key,model_family,eligible,suitability_score,deployment_role,reasons,requirements)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, series_key, rec["model_family"], rec["eligible"], rec["suitability_score"],
             rec["deployment_role"], Jsonb(rec["reasons"]), Jsonb(rec["requirements"])),
        )


def _profile_macro(cur, run_id: str, projects: pd.DataFrame, portfolio: pd.DataFrame) -> dict:
    profiled = 0
    signals = {"NO_ACTION": 0, "REVIEW": 0, "RETRAIN_CANDIDATE": 0, "BLOCKED": 0}
    groups = [("PORTFOLIO:ALL", "PORTFOLIO", "ALL", portfolio)]
    groups += [(f"PROJECT:{project}", "PROJECT", str(project), g.copy()) for project, g in projects.groupby("codigo_proyecto", sort=True)]
    for series_key, level, entity_id, g in groups:
        if not len(g):
            continue
        _insert_registry(
            cur, series_key=series_key, scope="MACRO", entity_level=level, entity_id=entity_id,
            target="ventas_mes", frequency="MONTHLY", source="forecasting_macro.v_project_month" if level == "PROJECT" else "forecasting_macro.v_portfolio_month",
            hierarchy="PORTFOLIO/PROJECT" if level == "PROJECT" else "PORTFOLIO",
            metadata={"evidence_level": "RECONSTRUCTED_REVISED_HISTORY", "point_in_time": False},
        )
        target_profile = None
        for variable in [v for v in MACRO_VARIABLES if v in g.columns]:
            p = profile_series(g, date_col="periodo_mes", value_col=variable, monthly=True)
            _insert_profile(cur, run_id, series_key, variable, "TARGET" if variable == "ventas_mes" else "FEATURE", p)
            profiled += 1
            if variable == "ventas_mes":
                target_profile = p
        if target_profile:
            _insert_recommendations(cur, run_id, series_key, recommend_models(target_profile, has_exogenous=False, hierarchy=True))

        target = pd.to_numeric(g["ventas_mes"], errors="coerce")
        psi = None
        mean_shift = None
        zero_delta = None
        status = "INSUFFICIENT_DATA"
        detail = {"policy": "last 6 complete months vs up to 12 preceding months"}
        if len(g) >= 12:
            current = target.iloc[-6:]
            reference = target.iloc[max(0, len(target)-18):-6]
            psi = population_stability_index(reference, current)
            if len(reference.dropna()) >= 5 and reference.std(ddof=1) not in (0, np.nan):
                sd = float(reference.std(ddof=1))
                if sd > 0:
                    mean_shift = float((current.mean() - reference.mean()) / sd)
            zero_delta = float(current.eq(0).mean() - reference.eq(0).mean()) if len(reference) else None
            if psi is None:
                status = "INSUFFICIENT_DATA"
            elif psi >= 0.25 or (mean_shift is not None and abs(mean_shift) >= 1.5):
                status = "ALERT"
            elif psi >= 0.10 or (mean_shift is not None and abs(mean_shift) >= 0.75):
                status = "WARN"
            else:
                status = "OK"
        cur.execute(
            """INSERT INTO forecasting_control.drift_metric
            (run_id,series_key,variable_name,reference_from,reference_to,current_from,current_to,psi,mean_shift_std,zero_rate_delta,status,detail)
            VALUES (%s,%s,'ventas_mes',%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, series_key,
             pd.to_datetime(g.periodo_mes).iloc[max(0, len(g)-18)].date() if len(g) >= 12 else None,
             pd.to_datetime(g.periodo_mes).iloc[-7].date() if len(g) >= 12 else None,
             pd.to_datetime(g.periodo_mes).iloc[-6].date() if len(g) >= 6 else None,
             pd.to_datetime(g.periodo_mes).iloc[-1].date() if len(g) else None,
             psi, mean_shift, zero_delta, status, Jsonb(detail)),
        )
        if target_profile and target_profile.get("missing_periods", 0) > 0:
            signal, reason = "BLOCKED", "Calendar gaps: repair data contract before fitting."
        elif status == "ALERT":
            signal, reason = "RETRAIN_CANDIDATE", "Distribution shift exceeded the review threshold; retrain only after temporal validation."
        elif status == "WARN":
            signal, reason = "REVIEW", "Moderate shift detected; compare champion and challengers before any promotion."
        else:
            signal, reason = "NO_ACTION", "No strong drift signal; keep scheduled evaluation and baseline comparison."
        signals[signal] += 1
        cur.execute(
            """INSERT INTO forecasting_control.retraining_signal
            (run_id,series_key,status,reason,evidence) VALUES (%s,%s,%s,%s,%s)""",
            (run_id, series_key, signal, reason, Jsonb({"drift_status": status, "psi": psi, "mean_shift_std": mean_shift})),
        )
    return {"profile_rows": profiled, "retraining_signals": signals}


def _profile_micro(cur, run_id: str, micro: pd.DataFrame) -> dict:
    if not len(micro):
        return {"profile_rows": 0, "projects": 0}
    rows = 0
    latest_observed = micro[micro.evidencia.eq("OBSERVADO")].copy()
    if len(latest_observed):
        latest_date = pd.to_datetime(latest_observed.fecha_corte).max()
        latest_observed = latest_observed[pd.to_datetime(latest_observed.fecha_corte).eq(latest_date)]
        # Avoid four copies of the same unit caused by the four outcome horizons.
        latest_observed = latest_observed.sort_values("horizonte_dias").drop_duplicates(["codigo_unidad", "fecha_corte"])
    for project, g in latest_observed.groupby("codigo_proyecto", sort=True):
        key = f"MICRO:PROJECT:{project}"
        _insert_registry(
            cur, series_key=key, scope="MICRO", entity_level="UNIT_POOL", entity_id=str(project),
            target="unit_sale_probability", frequency="DAILY_SNAPSHOT", source="forecasting_micro.v_unit_training",
            hierarchy=f"PORTFOLIO/PROJECT:{project}/UNIT", metadata={"point_in_time": True, "evidence_level": "OBSERVADO"},
        )
        observed_from = pd.to_datetime(g.fecha_corte).min().date() if len(g) else None
        observed_to = pd.to_datetime(g.fecha_corte).max().date() if len(g) else None
        for variable in [v for v in MICRO_VARIABLES if v in g.columns]:
            p = profile_numeric(g[variable])
            p.update({"observed_from": observed_from, "observed_to": observed_to, "missing_periods": 0})
            _insert_profile(cur, run_id, key, variable, "FEATURE", p, {"distribution_scope": "latest observed unit snapshot"})
            rows += 1

    for horizon in (30, 60, 90, 180):
        key = f"MICRO:PORTFOLIO:H{horizon}"
        h = micro[micro.horizonte_dias.eq(horizon) & micro.maduro & micro.venta_vigente.notna()]
        observed = h[h.evidencia.eq("OBSERVADO") & h.elegible_validacion_prospectiva.fillna(False)]
        reconstructed = h[h.evidencia.eq("RECONSTRUIDO")]
        eligible = len(observed) >= 200 and observed.fecha_corte.nunique() >= 4 and observed.venta_vigente.nunique() == 2
        shadow_ok = len(reconstructed) >= 80 and reconstructed.fecha_corte.nunique() >= 3 and reconstructed.venta_vigente.nunique() == 2
        score = 90 if eligible else (60 if shadow_ok else 20)
        role = "CANDIDATE" if eligible else ("SHADOW" if shadow_ok else "NOT_ELIGIBLE")
        reasons = [
            f"prospective observed mature rows={len(observed)} across cuts={observed.fecha_corte.nunique()}",
            f"reconstructed diagnostic rows={len(reconstructed)} across cuts={reconstructed.fecha_corte.nunique()}",
        ]
        _insert_registry(
            cur, series_key=key, scope="MICRO", entity_level="UNIT_POOL", entity_id="ALL",
            target="unit_sale_probability", frequency=f"HORIZON_{horizon}_DAYS", source="forecasting_micro.v_unit_training",
            hierarchy="PORTFOLIO/PROJECT/UNIT", metadata={"horizon_days": horizon},
        )
        _insert_recommendations(cur, run_id, key, [{
            "model_family": "micro_logit",
            "eligible": bool(eligible or shadow_ok),
            "suitability_score": score,
            "deployment_role": role,
            "reasons": reasons,
            "requirements": {"preferred_observed_rows": 200, "min_diagnostic_rows": 80, "temporal_embargo": True},
        }])
    return {"profile_rows": rows, "projects": int(latest_observed.codigo_proyecto.nunique()) if len(latest_observed) else 0}


def _store_micro_fit(cur, temporal_run_id: str, fit) -> int:
    cur.execute(
        """INSERT INTO forecasting_control.model_runs
        (model_run_id,temporal_run_id,scope,target_name,horizon,model_family,role,evidence_level,
         training_start,training_end,validation_start,validation_end,rows_train,rows_validation,
         metrics,feature_contract,artifact_path)
        VALUES (%s,%s,'MICRO','unit_sale_probability',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (fit.model_run_id, temporal_run_id, f"{fit.horizon_days}d", fit.model_family, fit.role, fit.evidence_level,
         fit.train_start, fit.train_end, fit.validation_start, fit.validation_end, fit.rows_train, fit.rows_validation,
         Jsonb(json_safe(fit.metrics)), Jsonb(json_safe(fit.feature_contract)), fit.artifact_path),
    )
    count = 0
    for row in fit.predictions.itertuples(index=False):
        info_cutoff = pd.Timestamp(row.information_cutoff).to_pydatetime()
        cur.execute(
            """INSERT INTO forecasting_micro.unit_sale_probability
            (model_run_id,codigo_unidad,codigo_proyecto,origin_date,horizon_days,model_family,probability,
             is_selected,evidence_level,information_cutoff,metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s)""",
            (fit.model_run_id, str(row.codigo_unidad), str(row.codigo_proyecto), pd.Timestamp(row.fecha_corte).date(),
             fit.horizon_days, fit.model_family, float(row.probability), fit.evidence_level, info_cutoff,
             Jsonb({"role": fit.role, "selection_metrics": json_safe(fit.metrics)})),
        )
        count += 1
    return count


def already_ran_today(conn, mode: str = "CLOSED_LOOP") -> bool:
    today = datetime.now(LIMA).date()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT EXISTS(SELECT 1 FROM forecasting_control.temporal_runs
            WHERE as_of_date=%s AND mode=%s AND status IN ('OK','PARTIAL'))""",
            (today, mode),
        )
        return bool(cur.fetchone()[0])


def run_internal(conn, root: Path, output: Path, *, mode: str = "CLOSED_LOOP", once_per_day: bool = False) -> dict:
    ensure_schema(conn, root)
    if once_per_day and already_ran_today(conn, mode):
        return {"status": "SKIPPED_ALREADY_RAN_TODAY", "run_id": None}
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext('medallio_temporal_science'))")
        if not cur.fetchone()[0]:
            return {"status": "SKIPPED_LOCKED", "run_id": None}

    projects, portfolio = read_macro(conn)
    micro = read_micro(conn)
    run_id = str(uuid4())
    now = datetime.now(LIMA)
    fingerprint = _source_fingerprint(projects, micro)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO forecasting_control.temporal_runs
            (run_id,mode,as_of_date,information_cutoff,status,source_semantics,source_fingerprint,detail)
            VALUES (%s,%s,%s,%s,'RUNNING','MIXED_RECONSTRUCTED_AND_OBSERVED',%s,%s)""",
            (run_id, mode, now.date(), now, fingerprint, Jsonb({"macro_rows": len(projects), "micro_rows": len(micro)})),
        )
    conn.commit()

    try:
        with conn.cursor() as cur:
            macro_summary = _profile_macro(cur, run_id, projects, portfolio)
            micro_summary = _profile_micro(cur, run_id, micro)
            emitted = 0
            model_runs = 0
            for horizon in (30, 60, 90, 180):
                fit = fit_micro_horizon(micro, horizon, output / run_id)
                if fit is not None:
                    emitted += _store_micro_fit(cur, run_id, fit)
                    model_runs += 1
            summary = {
                "macro": macro_summary,
                "micro": micro_summary,
                "micro_model_runs": model_runs,
                "micro_probabilities_emitted": emitted,
                "source_fingerprint": fingerprint,
                "macro_model": "delegated to existing commercial_forecasting robust policy",
            }
            cur.execute(
                """UPDATE forecasting_control.temporal_runs
                SET status='OK', finished_at=clock_timestamp(), detail=detail || %s
                WHERE run_id=%s""",
                (Jsonb(json_safe(summary)), run_id),
            )
        conn.commit()
        return {"status": "OK", "run_id": run_id, **summary}
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE forecasting_control.temporal_runs
                SET status='FAILED', finished_at=clock_timestamp(), detail=detail || %s
                WHERE run_id=%s""",
                (Jsonb({"error": f"{type(exc).__name__}: {exc}"}), run_id),
            )
        conn.commit()
        raise


def record_macro_result(conn, run_id: str, *, returncode: int, stdout_tail: str, stderr_tail: str) -> None:
    payload = {
        "macro_forecasting_returncode": returncode,
        "macro_forecasting_stdout_tail": stdout_tail[-4000:],
        "macro_forecasting_stderr_tail": stderr_tail[-4000:],
    }
    status = "OK" if returncode == 0 else "PARTIAL"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE forecasting_control.temporal_runs
            SET status=%s, detail=detail || %s, finished_at=clock_timestamp()
            WHERE run_id=%s""",
            (status, Jsonb(payload), run_id),
        )
    conn.commit()


def status(conn, limit: int = 10) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT run_id,as_of_date,started_at,finished_at,status,source_semantics,
               profiled_series,model_runs,series_needing_attention,detail
               FROM forecasting_control.v_system_status
               ORDER BY started_at DESC LIMIT %s""",
            (limit,),
        )
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
