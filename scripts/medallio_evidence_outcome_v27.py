from __future__ import annotations

import csv
import json
import math
import os
import hashlib
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


LEVELS = [
    ("OBSERVED", 1, "Visibilidad & Reporting", "¿Qué pasó?"),
    ("DIAGNOSTIC", 2, "Diagnóstico & Comparabilidad", "¿Por qué pasó?"),
    ("PREDICTIVE", 3, "Predicción & Forward View", "¿Qué probablemente pasará?"),
    ("RECOMMENDATION", 4, "Decision Intelligence", "¿Qué deberíamos hacer?"),
    ("ECONOMIC_DECISION", 5, "Optimización Económica", "¿Cuánto valor está en juego?"),
    ("CAUSAL_LEARNING", 6, "Aprendizaje Causal", "¿La acción realmente generó mejora?"),
    ("CLOSED_LOOP", 7, "Closed-loop Growth OS", "¿Cómo aprende y reasigna recursos el sistema?"),
]

STATUS_ORDER = {"PASS": 2, "WARN": 1, "BLOCK": 0}


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _norm(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _as_float(value: Any):
    if value is None or value == "":
        return None
    try:
        x = float(value)
        if math.isnan(x):
            return None
        return x
    except Exception:
        return None


def _ratio01(value: Any):
    x = _as_float(value)
    if x is None:
        return None
    if x > 1.5:
        x = x / 100.0
    return min(max(x, 0.0), 1.0)


def _read_table(path: Path, nrows=10000):
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path, nrows=nrows)
        if path.suffix.lower() == ".xlsx":
            return pd.read_excel(path, nrows=nrows)
    except Exception:
        return None
    return None


def _find_col(df, aliases=(), contains=()):
    norm = {_norm(c): c for c in df.columns}
    for a in aliases:
        if _norm(a) in norm:
            return norm[_norm(a)]
    for c in df.columns:
        lc = _norm(c)
        for group in contains:
            if all(tok in lc for tok in group):
                return c
    return None


def _project_col(df):
    return _find_col(
        df,
        aliases=("nombre_proyecto", "proyecto", "codigo_proyecto", "project", "project_name", "project_code"),
        contains=(("proyecto",), ("project",)),
    )


def _metric_col(df, role):
    specs = {
        "stock_units": (("stock", "stock_inicial", "stock_units"), (("stock",),)),
        "stock_value": (
            ("valor_stock", "stock_value", "monto_stock", "valor_por_vender", "monto_por_vender"),
            (("stock", "valor"), ("stock", "monto"), ("por_vender", "monto"), ("por_vender", "valor")),
        ),
        "sales_units": (
            ("ventas", "ventas_unidades", "sales_units", "minutas", "separaciones"),
            (("venta",), ("minuta",), ("separ",)),
        ),
        "sales_value": (
            ("monto_vendido", "ventas_soles", "revenue_actual", "valor_vendido", "importe_vendido"),
            (("venta", "monto"), ("venta", "sol"), ("revenue", "actual"), ("valor", "vend")),
        ),
        "absorption_rate": (
            ("absorcion", "absorcion_rate", "absorption_rate", "ritmo_venta"),
            (("absor",), ("ritmo",)),
        ),
        "months_to_zero": (
            ("meses_stock_cero", "months_to_zero", "cobertura_meses", "meses_cobertura"),
            (("meses", "stock"), ("coverage", "months"), ("cobertura", "meses")),
        ),
        "avg_price_m2": (
            ("precio_m2", "precio_m2_ajustado", "avg_price_m2", "p_m2"),
            (("precio", "m2"), ("price", "m2")),
        ),
        "forecast_units": (
            ("forecast_units", "pronostico_ventas", "forecast_ventas"),
            (("forecast", "unit"), ("forecast", "venta"), ("pronost", "venta")),
        ),
        "forecast_wape_pct": (
            ("wape", "forecast_wape", "wape_pct"),
            (("wape",),),
        ),
        "target_value": (
            ("meta", "target", "goal", "meta_monto", "monto_meta", "meta_ventas"),
            (("meta", "monto"), ("target", "value"), ("goal", "value")),
        ),
        "gap_value": (
            ("gap", "gap_soles", "brecha", "brecha_soles", "gap_monto", "valor_gap"),
            (("gap", "monto"), ("gap", "sol"), ("brecha", "monto"), ("brecha", "sol")),
        ),
        "value_to_capture": (
            ("value_to_capture", "valor_capturable", "impacto_potencial", "impact_value", "valor_incremental"),
            (("impacto", "sol"), ("impact", "value"), ("valor", "incremental"), ("value", "capture")),
        ),
        "action_cost": (
            ("action_cost", "costo_accion", "cost", "costo", "investment", "inversion"),
            (("costo", "accion"), ("action", "cost"), ("investment", "value")),
        ),
        "uplift_pct": (
            ("uplift_pct", "uplift", "mejora_conversion", "conversion_uplift", "mejora_pct"),
            (("uplift",), ("mejora", "conversion")),
        ),
        "confidence": (
            ("confidence", "confianza", "probability", "probabilidad", "confidence_score"),
            (("confidence",), ("confianza",), ("probabilidad",)),
        ),
        "expected_roi": (
            ("roi", "expected_roi", "roi_esperado", "return_on_investment"),
            (("roi",),),
        ),
    }
    aliases, contains = specs[role]
    return _find_col(df, aliases=aliases, contains=contains)


def _agg(group, col, kind="mean"):
    if not col or col not in group.columns:
        return None
    s = pd.to_numeric(group[col], errors="coerce").dropna()
    if s.empty:
        return None
    return float(s.sum() if kind == "sum" else s.mean())




@contextmanager
def medallio_db_connection():
    """
    Runtime bridge:
    1) explicit DSN/env if configured;
    2) repository-native settings + connect_postgres otherwise.

    Important: only CONNECT errors are wrapped here.
    SQL errors raised by the caller must propagate unchanged so diagnostics
    show the actual failing relation/column/constraint.
    """
    dsn = _dsn_from_env()
    if dsn:
        import psycopg
        try:
            conn = psycopg.connect(dsn)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo abrir PostgreSQL por DSN/env: {type(exc).__name__}: {exc}"
            ) from exc
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return

    try:
        from replica_cygnus.connections import connect_postgres
        from replica_cygnus.settings import load_settings
        settings = load_settings()
        conn = connect_postgres(settings)
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo abrir PostgreSQL por replica_cygnus settings: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    # connect_postgres may return either a connection or a context manager.
    if hasattr(conn, "__enter__") and hasattr(conn, "__exit__"):
        with conn as active_conn:
            yield active_conn
    else:
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass


def load_project_growth_state_from_db(slot: str):
    """
    Prefer the governed SQL view when available.
    This is what makes L2 depend on a real comparable project contract
    instead of accidental CSV column discovery.
    """
    try:
        with medallio_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        project_key,
                        project_name,
                        stock_units,
                        stock_value,
                        last_complete_sales_units AS sales_units,
                        NULL::numeric AS sales_value,
                        absorption_rate,
                        months_to_zero,
                        NULL::numeric AS avg_price_m2,
                        forecast_units,
                        forecast_wape_pct,
                        target_value,
                        gap_value,
                        value_to_capture,
                        action_cost,
                        uplift_pct,
                        confidence,
                        expected_roi,
                        data_quality_status,
                        evidence_gaps,
                        attention_score,
                        suggested_action,
                        suggested_owner,
                        suggested_urgency,
                        outcome_required,
                        roi_required,
                        suggested_outcome_metric,
                        snapshot_date,
                        latest_complete_period,
                        'analytics.v_project_growth_state'::text AS source_artifact
                    FROM analytics.v_project_growth_state
                    ORDER BY attention_score DESC, gap_value DESC NULLS LAST, project_key
                """)
                cols = [c.name for c in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for row in rows:
            row["snapshot_ts"] = str(row.get("snapshot_date") or "")
            row["slot"] = slot
            row["trust_score_pct"] = None
            row["evidence_grade"] = None
        return rows
    except Exception:
        return []


def load_ceo_growth_actions_from_db():
    try:
        with medallio_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        project_key,
                        project_name,
                        attention_score,
                        decision,
                        owner,
                        urgency,
                        value_at_stake_soles,
                        value_at_stake_type,
                        confidence_label,
                        why,
                        suggested_outcome_metric,
                        outcome_required,
                        roi_required,
                        decision_level
                    FROM decision_intelligence.v_ceo_growth_decision_queue
                    ORDER BY attention_score DESC, value_at_stake_soles DESC NULLS LAST, project_key
                    LIMIT 10
                """)
                cols = [c.name for c in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        return []


def inject_governed_decisions(digest: dict, actions: list[dict]):
    if not actions:
        return digest

    original = list(digest.get("decisions") or [])
    digest["decisions_original"] = original

    governed = []
    for a in actions[:3]:
        governed.append({
            "decision": a.get("decision"),
            "owner": a.get("owner"),
            "why": a.get("why"),
            "project": a.get("project_key"),
            "project_name": a.get("project_name"),
            "urgency": a.get("urgency"),
            "value_at_stake": a.get("value_at_stake_soles"),
            "value_at_stake_type": a.get("value_at_stake_type"),
            "confidence": a.get("confidence_label"),
            "suggested_outcome_metric": a.get("suggested_outcome_metric"),
            "outcome_required": bool(a.get("outcome_required")),
            "roi_required": bool(a.get("roi_required")),
            "decision_level": a.get("decision_level") or "D1_RECOMMEND",
        })

    digest["decisions"] = governed
    digest["governed_actions"] = actions
    return digest


def discover_project_growth_state(files: list[Path], summary: dict, slot: str):
    rows = []
    for path in files:
        if path.suffix.lower() not in {".csv", ".xlsx"}:
            continue
        df = _read_table(path, nrows=10000)
        if df is None or df.empty:
            continue
        pcol = _project_col(df)
        if not pcol:
            continue

        cols = {role: _metric_col(df, role) for role in [
            "stock_units", "stock_value", "sales_units", "sales_value",
            "absorption_rate", "months_to_zero", "avg_price_m2",
            "forecast_units", "forecast_wape_pct", "target_value",
            "gap_value", "value_to_capture", "action_cost", "uplift_pct",
            "confidence", "expected_roi",
        ]}
        if not any(cols.values()):
            continue

        work = df.copy()
        work[pcol] = work[pcol].astype("string")
        for project, group in work.groupby(pcol, dropna=True):
            row = {
                "snapshot_ts": datetime.now(timezone.utc).isoformat(),
                "slot": slot,
                "project_key": str(project),
                "project_name": str(project),
                "source_artifact": path.name,
                "trust_score_pct": _as_float(summary.get("trust_score_pct")),
                "evidence_grade": None,
            }
            for role, col in cols.items():
                kind = "sum" if role in {"stock_units", "stock_value", "sales_units", "sales_value", "target_value", "gap_value", "value_to_capture", "action_cost"} else "mean"
                row[role] = _agg(group, col, kind=kind)

            if row["gap_value"] is None and row["target_value"] is not None and row["sales_value"] is not None:
                row["gap_value"] = max(row["target_value"] - row["sales_value"], 0.0)

            rows.append(row)

    best = {}
    for row in rows:
        key = row["project_key"]
        completeness = sum(v is not None for k, v in row.items() if k not in {"snapshot_ts", "slot", "project_key", "project_name", "source_artifact"})
        if key not in best or completeness > best[key][0]:
            best[key] = (completeness, row)

    return [v[1] for v in best.values()]


def _decision_owner(d):
    return d.get("owner") or d.get("responsible") or d.get("responsable") or ""


def _decision_reason(d):
    return d.get("why") or d.get("evidence") or d.get("rationale") or ""


def build_decision_ledger(digest: dict, project_states: list[dict], slot: str):
    project_map = {r["project_key"]: r for r in project_states}
    decisions = []
    source_decisions = digest.get("decisions") or []

    if not source_decisions and project_states:
        for ps in project_states[:5]:
            source_decisions.append({
                "decision": f"Revisar crecimiento y economics de {ps['project_name']}",
                "owner": "",
                "why": "Señal económica detectada en artifacts de la corrida.",
                "project": ps["project_name"],
            })

    for idx, d in enumerate(source_decisions[:12], start=1):
        title = d.get("decision") or d.get("signal") or f"Decision {idx}"
        project = str(d.get("project") or d.get("proyecto") or "Portfolio")
        ps = project_map.get(project) or {}

        value_at_risk = ps.get("gap_value")
        exposure = ps.get("stock_value")
        value_to_capture = ps.get("value_to_capture")
        uplift = _ratio01(ps.get("uplift_pct"))
        if value_to_capture is None and value_at_risk is not None and uplift is not None:
            value_to_capture = value_at_risk * uplift

        confidence = _ratio01(ps.get("confidence"))
        action_cost = ps.get("action_cost")
        expected_roi = ps.get("expected_roi")
        if expected_roi is None and value_to_capture is not None and action_cost not in (None, 0):
            expected_roi = (value_to_capture - action_cost) / action_cost

        adjusted = value_to_capture * confidence if value_to_capture is not None and confidence is not None else None

        missing = []
        if not _decision_owner(d):
            missing.append("owner")
        if not _decision_reason(d):
            missing.append("rationale")
        if value_at_risk is None and exposure is None:
            missing.append("economic_exposure")
        if value_to_capture is None:
            missing.append("value_to_capture")
        if action_cost is None:
            missing.append("action_cost")
        if confidence is None:
            missing.append("measured_confidence")
        if expected_roi is None:
            missing.append("expected_roi")
        missing.append("realized_outcome")

        if value_to_capture is not None and action_cost is not None and confidence is not None:
            quantification_status = "quantified"
        elif any(x is not None for x in [value_at_risk, exposure, value_to_capture]):
            quantification_status = "partially_quantified"
        else:
            quantification_status = "unquantified"

        payload = {
            "slot": slot,
            "project": project,
            "title": title,
            "owner": _decision_owner(d),
            "reason": _decision_reason(d),
        }
        decision_id = f"dec_{_hash(payload)}"

        decisions.append({
            "decision_id": decision_id,
            "decision_ts": datetime.now(timezone.utc).isoformat(),
            "slot": slot,
            "project_key": project,
            "challenge": d.get("challenge") or "Growth",
            "decision_title": title,
            "decision_rationale": _decision_reason(d),
            "owner": _decision_owner(d),
            "deadline": d.get("deadline") or "",
            "decision_status": d.get("status") or "PROPOSED",
            "decision_level": "D1_RECOMMEND",
            "value_at_risk": value_at_risk,
            "economic_exposure": exposure,
            "value_to_capture": value_to_capture,
            "action_cost": action_cost,
            "confidence": confidence,
            "expected_roi": expected_roi,
            "confidence_adjusted_value": adjusted,
            "quantification_status": quantification_status,
            "missing_evidence": ", ".join(sorted(set(missing))),
            "source_artifact": ps.get("source_artifact") or "ceo_decision_queue",
        })
    return decisions


def artifact_evidence_signals(files: list[Path]):
    names = " ".join(p.name.lower() for p in files)
    columns = []
    for p in files:
        if p.suffix.lower() not in {".csv", ".xlsx"}:
            continue
        df = _read_table(p, nrows=50)
        if df is not None:
            columns.extend(_norm(c) for c in df.columns)
    text = names + " " + " ".join(columns)
    return {
        "has_project_data": any(x in text for x in ["proyecto", "project"]),
        "has_forecast": any(x in text for x in ["forecast", "wape", "bias", "pronost"]),
        "has_economics": any(x in text for x in ["gap", "meta", "target", "value_to_capture", "valor_capturable", "roi", "costo", "cost"]),
        "has_causal": any(x in text for x in ["treatment", "control", "baseline", "experiment", "causal", "challenger"]),
        "has_outcome": any(x in text for x in ["outcome", "realized", "resultado_real", "uplift_real"]),
    }



def _date_col(df):
    return _find_col(
        df,
        aliases=(
            "periodo_mes", "periodo", "fecha", "fecha_mes", "month",
            "period", "forecast_period", "target_month", "mes"
        ),
        contains=(("period",), ("fecha",), ("month",), ("mes",)),
    )


def _forecast_col(df):
    return _find_col(
        df,
        aliases=(
            "forecast", "forecast_units", "forecast_ventas",
            "pronostico", "pronostico_ventas", "prediction", "prediccion"
        ),
        contains=(("forecast",), ("pronost",), ("prediction",), ("predic",)),
    )


def _actual_col(df):
    return _find_col(
        df,
        aliases=(
            "actual", "actual_units", "ventas_reales", "ventas_actuales",
            "observed", "realized", "y_true", "ventas"
        ),
        contains=(("actual",), ("observ",), ("realiz",), ("venta", "real")),
    )


def _explicit_maturity_col(df):
    return _find_col(
        df,
        aliases=(
            "mature_for_evaluation", "period_complete", "mes_completo",
            "actual_available", "outcome_mature", "maduro"
        ),
        contains=(("mature",), ("complete",), ("mes", "completo"), ("maduro",)),
    )


def forecast_evaluation_maturity(files: list[Path]):
    """
    Evalúa forecast sólo con periodos maduros.
    Regla conservadora:
      - si existe flag explícito, lo respeta;
      - si no, excluye el mes calendario actual;
      - calcula WAPE únicamente sobre filas con forecast y actual observados.
    """
    now = datetime.now().date()
    current_ym = (now.year, now.month)
    all_rows = []

    for path in files:
        if path.suffix.lower() not in {".csv", ".xlsx"}:
            continue
        df = _read_table(path, nrows=50000)
        if df is None or df.empty:
            continue

        fcol = _forecast_col(df)
        acol = _actual_col(df)
        dcol = _date_col(df)
        mcol = _explicit_maturity_col(df)

        if not fcol or not acol:
            continue

        work = pd.DataFrame({
            "forecast": pd.to_numeric(df[fcol], errors="coerce"),
            "actual": pd.to_numeric(df[acol], errors="coerce"),
        })

        if dcol:
            parsed = pd.to_datetime(df[dcol], errors="coerce")
            work["period"] = parsed
        else:
            work["period"] = pd.NaT

        if mcol:
            raw = df[mcol]
            if pd.api.types.is_bool_dtype(raw):
                mature = raw.fillna(False)
            else:
                mature = raw.astype("string").str.strip().str.lower().isin(
                    ["1", "true", "t", "yes", "y", "si", "sí", "mature", "maduro", "complete", "completo"]
                )
        elif dcol:
            mature = work["period"].apply(
                lambda x: bool(pd.notna(x) and (x.year, x.month) < current_ym)
            )
        else:
            # Sin periodo ni flag explícito no afirmamos madurez.
            mature = pd.Series(False, index=work.index)

        work["mature_for_evaluation"] = mature
        work["source_artifact"] = path.name
        all_rows.append(work)

    if not all_rows:
        return {
            "mature_rows": 0,
            "immature_rows_excluded": 0,
            "mature_wape_pct": None,
            "source_rows": 0,
            "status": "NO_EVALUABLE_FORECAST_ROWS",
            "detail_rows": [],
        }

    full = pd.concat(all_rows, ignore_index=True)
    evaluable = full[
        full["mature_for_evaluation"]
        & full["forecast"].notna()
        & full["actual"].notna()
    ].copy()

    immature = full[
        (~full["mature_for_evaluation"])
        & full["forecast"].notna()
    ].copy()

    wape = None
    denom = evaluable["actual"].abs().sum()
    if not evaluable.empty and denom > 0:
        wape = float(
            (evaluable["actual"] - evaluable["forecast"]).abs().sum()
            / denom * 100.0
        )

    detail_rows = []
    for _, r in full.head(5000).iterrows():
        detail_rows.append({
            "source_artifact": r.get("source_artifact"),
            "period": (
                r["period"].strftime("%Y-%m")
                if pd.notna(r.get("period")) else None
            ),
            "forecast": _as_float(r.get("forecast")),
            "actual": _as_float(r.get("actual")),
            "mature_for_evaluation": bool(r.get("mature_for_evaluation")),
        })

    return {
        "mature_rows": int(len(evaluable)),
        "immature_rows_excluded": int(len(immature)),
        "mature_wape_pct": wape,
        "source_rows": int(len(full)),
        "status": "OK" if wape is not None else "NO_MATURE_WAPE",
        "detail_rows": detail_rows,
    }


def _truthy_series(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype("string").str.strip().str.lower().isin(
        ["1", "true", "t", "yes", "y", "si", "sí", "mature", "maduro", "complete", "completed", "completo"]
    )


def causal_evidence_from_artifacts(files: list[Path]):
    """
    No acepta sólo nombres de columnas.
    Requiere filas reales con:
      experiment/treatment + control/challenger + baseline + outcome observado/maduro.
    """
    experiments = 0
    mature_outcomes = 0
    linked_complete = 0
    evidence_rows = []

    for path in files:
        if path.suffix.lower() not in {".csv", ".xlsx"}:
            continue
        df = _read_table(path, nrows=50000)
        if df is None or df.empty:
            continue

        treatment = _find_col(
            df,
            aliases=("treatment", "treatment_name", "tratamiento"),
            contains=(("treatment",), ("tratamiento",)),
        )
        control = _find_col(
            df,
            aliases=("control", "control_name", "challenger", "grupo_control"),
            contains=(("control",), ("challenger",)),
        )
        baseline = _find_col(
            df,
            aliases=("baseline", "baseline_value", "valor_baseline"),
            contains=(("baseline",),),
        )
        outcome = _find_col(
            df,
            aliases=(
                "observed_value", "outcome_value", "realized_outcome",
                "resultado_real", "value_realized", "uplift_real"
            ),
            contains=(
                ("observed", "value"), ("outcome", "value"),
                ("realized",), ("resultado", "real"), ("uplift", "real")
            ),
        )
        maturity = _find_col(
            df,
            aliases=("maturity_status", "outcome_mature", "mature", "maduro"),
            contains=(("maturity",), ("mature",), ("maduro",)),
        )

        if not any([treatment, control, baseline, outcome]):
            continue

        work = df.copy()
        exp_mask = pd.Series(True, index=work.index)
        for col in [treatment, control, baseline]:
            if col:
                exp_mask &= work[col].notna()
            else:
                exp_mask &= False

        outcome_mask = work[outcome].notna() if outcome else pd.Series(False, index=work.index)
        if maturity:
            mature_mask = _truthy_series(work[maturity]) | work[maturity].astype("string").str.upper().eq("MATURE")
        else:
            # Sin flag de madurez no damos PASS causal; sólo evidencia parcial.
            mature_mask = pd.Series(False, index=work.index)

        experiments += int(exp_mask.sum())
        mature_outcomes += int((outcome_mask & mature_mask).sum())
        linked_complete += int((exp_mask & outcome_mask & mature_mask).sum())

        evidence_rows.append({
            "source_artifact": path.name,
            "experiment_rows": int(exp_mask.sum()),
            "outcome_rows": int(outcome_mask.sum()),
            "mature_outcome_rows": int((outcome_mask & mature_mask).sum()),
            "linked_complete_rows": int((exp_mask & outcome_mask & mature_mask).sum()),
        })

    return {
        "experiment_rows": experiments,
        "mature_outcome_rows": mature_outcomes,
        "linked_complete_rows": linked_complete,
        "artifact_evidence": evidence_rows,
    }


def causal_evidence_from_db():
    """
    Complementa artifacts con evidencia persistida.
    Si la conexión no está disponible, no falla el briefing.
    """
    try:
        with medallio_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*)
                    FROM experiments.baseline_challenger
                    WHERE treatment_name IS NOT NULL
                      AND control_name IS NOT NULL
                      AND baseline_value IS NOT NULL
                """)
                experiments = int(cur.fetchone()[0])

                cur.execute("""
                    SELECT count(*)
                    FROM decision_intelligence.outcome_ledger
                    WHERE observed_value IS NOT NULL
                      AND maturity_status = 'MATURE'
                """)
                outcomes = int(cur.fetchone()[0])

                cur.execute("""
                    SELECT count(*)
                    FROM experiments.baseline_challenger e
                    JOIN decision_intelligence.outcome_ledger o
                      ON o.decision_id = e.decision_id
                    WHERE e.treatment_name IS NOT NULL
                      AND e.control_name IS NOT NULL
                      AND e.baseline_value IS NOT NULL
                      AND o.observed_value IS NOT NULL
                      AND o.maturity_status = 'MATURE'
                """)
                linked = int(cur.fetchone()[0])

        return {
            "db_available": True,
            "experiment_rows": experiments,
            "mature_outcome_rows": outcomes,
            "linked_complete_rows": linked,
        }
    except Exception as exc:
        return {
            "db_available": False,
            "experiment_rows": 0,
            "mature_outcome_rows": 0,
            "linked_complete_rows": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def real_causal_evidence(files: list[Path]):
    art = causal_evidence_from_artifacts(files)
    db = causal_evidence_from_db()
    return {
        "artifact": art,
        "db": db,
        "experiment_rows": max(art["experiment_rows"], db["experiment_rows"]),
        "mature_outcome_rows": max(art["mature_outcome_rows"], db["mature_outcome_rows"]),
        "linked_complete_rows": max(art["linked_complete_rows"], db["linked_complete_rows"]),
    }


def gate_score(status):
    return {"PASS": 100, "WARN": 50, "BLOCK": 0}.get(str(status).upper(), 0)


def _safe_unlink(path: Path):
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def write_calibrated_ceo_visuals(root: Path, gates: list[dict], gate_summary: dict, decision_rows: list[dict]):
    """
    Sobrescribe los dos gráficos engañosos de 100% con evidencia real.
    Value at Stake sólo existe si hay al menos una decisión cuantificada.
    """
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return {"status": "NO_MATPLOTLIB"}

    out = root / "artifacts" / "medallio_ceo_briefing"
    out.mkdir(parents=True, exist_ok=True)

    ordered = sorted(gates, key=lambda x: x["level_number"])
    labels = [f"L{g['level_number']} {g['gate_name']}" for g in ordered]
    local_scores = [gate_score(g["gate_status"]) for g in ordered]

    current_level = int(gate_summary.get("growth_altitude_level") or 0)
    sequential_scores = []
    for g in ordered:
        lvl = int(g["level_number"])
        if lvl <= current_level:
            sequential_scores.append(100)
        elif lvl == current_level + 1 and g["gate_status"] == "WARN":
            sequential_scores.append(50)
        else:
            sequential_scores.append(0)

    # 00_ceo_layer_readiness.png — madurez secuencial validada
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(labels, sequential_scores)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% de madurez validada por cadena de evidencia")
    ax.set_title("Readiness de Medallio — Evidence Gate calibrado")
    for i, v in enumerate(sequential_scores):
        ax.text(min(v + 2, 98), i, f"{v}%", va="center")
    fig.tight_layout()
    fig.savefig(out / "00_ceo_layer_readiness.png", dpi=160)
    plt.close(fig)

    # 09_ceo_heatmap.png — capacidad local, sin confundirla con altitud secuencial
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(labels, local_scores)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score observable del gate (%)")
    ax.set_title("CEO Heatmap — evidencia observable por gate")
    for i, (v, g) in enumerate(zip(local_scores, ordered)):
        ax.text(min(v + 2, 98), i, f"{g['gate_status']} · {v}%", va="center")
    fig.tight_layout()
    fig.savefig(out / "09_ceo_heatmap.png", dpi=160)
    plt.close(fig)

    quantified = [
        r for r in decision_rows
        if r.get("quantification_status") == "quantified"
        and r.get("value_to_capture") is not None
    ]

    # Value at Stake: nunca mantener una ilustración sin sustento.
    for p in out.glob("01_value_at_stake*.png"):
        _safe_unlink(p)

    value_status = {
        "generated": False,
        "reason": "NO_QUANTIFIED_ECONOMIC_DECISIONS",
        "quantified_decisions": len(quantified),
    }

    if quantified:
        names = [str(r.get("project_key") or r.get("decision_title"))[:35] for r in quantified[:8]]
        values = [float(r["value_to_capture"]) for r in quantified[:8]]
        fig, ax = plt.subplots(figsize=(11, 6))
        ax.barh(names, values)
        ax.set_xlabel("Value to Capture cuantificado")
        ax.set_title("Value at Stake — sólo decisiones económicamente cuantificadas")
        fig.tight_layout()
        fig.savefig(out / "01_value_at_stake.png", dpi=160)
        plt.close(fig)
        value_status = {
            "generated": True,
            "reason": "QUANTIFIED_EVIDENCE_AVAILABLE",
            "quantified_decisions": len(quantified),
        }

    (out / "value_at_stake_status.json").write_text(
        json.dumps(value_status, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "status": "OK",
        "readiness_chart": str(out / "00_ceo_layer_readiness.png"),
        "heatmap_chart": str(out / "09_ceo_heatmap.png"),
        "value_at_stake": value_status,
    }



def build_evidence_gates(digest: dict, files: list[Path], project_states: list[dict], decision_rows: list[dict], slot: str):
    s = digest.get("summary") or {}
    signals = artifact_evidence_signals(files)

    coverage = _as_float(s.get("platform_coverage_pct"))
    trust = _as_float(s.get("trust_score_pct"))

    v28 = digest.get("v28") or {}
    predictive_gate = v28.get("gate") or {}

    if v28.get("status") == "OK":
        forecast_eval = {
            "mature_rows": predictive_gate.get("mature_pairs", 0),
            "immature_rows_excluded": None,
            "mature_wape_pct": predictive_gate.get("global_wape_pct"),
            "mature_bias_pct": predictive_gate.get("global_bias_pct"),
            "projects_with_mature": predictive_gate.get("projects_with_mature", 0),
            "defensible_cells": predictive_gate.get("defensible_cells", 0),
            "status": predictive_gate.get("gate_status"),
            "source": "analytics.v_forecast_predictive_gate",
        }
    else:
        forecast_eval = forecast_evaluation_maturity(files)

    # v2.8 prefers frozen forecast→actual evaluation from PostgreSQL.
    wape = _as_float(forecast_eval.get("mature_wape_pct"))

    causal = real_causal_evidence(files)

    owner_ratio = 0.0
    rationale_ratio = 0.0
    if decision_rows:
        owner_ratio = sum(bool(r.get("owner")) for r in decision_rows) / len(decision_rows)
        rationale_ratio = sum(bool(r.get("decision_rationale")) for r in decision_rows) / len(decision_rows)

    quantified = sum(r.get("quantification_status") == "quantified" for r in decision_rows)
    partial = sum(r.get("quantification_status") == "partially_quantified" for r in decision_rows)

    gates = []

    def add(level, status, score, threshold, reason, missing):
        spec = next(x for x in LEVELS if x[0] == level)
        gates.append({
            "gate_id": f"gate_{_hash({'slot': slot, 'level': level, 'reason': reason})}",
            "gate_ts": datetime.now(timezone.utc).isoformat(),
            "slot": slot,
            "claim_level": level,
            "level_number": spec[1],
            "gate_name": spec[2],
            "question": spec[3],
            "gate_status": status,
            "score": score,
            "threshold": threshold,
            "reason": reason,
            "missing_evidence": ", ".join(missing),
        })

    # L1 — observado
    if coverage is not None and coverage >= 95 and files:
        add("OBSERVED", "PASS", coverage, 95, "Cobertura alta y artifacts frescos disponibles.", [])
    elif coverage is not None and coverage >= 80:
        add("OBSERVED", "WARN", coverage, 95, "Cobertura razonable pero no suficiente para verdad ejecutiva fuerte.", ["coverage>=95"])
    else:
        add("OBSERVED", "BLOCK", coverage, 95, "No hay cobertura suficiente o no existen artifacts frescos.", ["coverage", "fresh_artifacts"])

    # L2 — diagnóstico
    if project_states and (coverage or 0) >= 90:
        add("DIAGNOSTIC", "PASS", len(project_states), 1, "Existe comparabilidad por proyecto con métricas observables.", [])
    elif signals["has_project_data"]:
        add("DIAGNOSTIC", "WARN", len(project_states), 1, "Hay datos por proyecto pero faltan métricas comparables consolidadas.", ["project_growth_state"])
    else:
        add("DIAGNOSTIC", "BLOCK", 0, 1, "No existe evidencia comparable por proyecto.", ["project_growth_state"])

    # L3 — v2.8 Predictive Gate: issued forecasts matched to mature outcomes.
    if v28.get("status") == "OK" and predictive_gate:
        pg_status = str(predictive_gate.get("gate_status") or "BLOCK").upper()
        pg_score = _as_float(predictive_gate.get("gate_score"))
        pg_reason = (
            predictive_gate.get("gate_reason")
            or "Predictive Gate sin explicación."
        )

        missing = []
        if int(predictive_gate.get("mature_pairs") or 0) < 12:
            missing.append("mature_pairs>=12")
        if int(predictive_gate.get("projects_with_mature") or 0) < 3:
            missing.append("projects_with_mature>=3")
        if int(predictive_gate.get("defensible_cells") or 0) < 3:
            missing.append("defensible_project_horizon_cells>=3")
        if predictive_gate.get("global_wape_pct") is None or float(predictive_gate.get("global_wape_pct")) > 25:
            missing.append("WAPE<=25")
        if predictive_gate.get("global_bias_pct") is None or abs(float(predictive_gate.get("global_bias_pct"))) > 15:
            missing.append("|Bias|<=15")
        if predictive_gate.get("leakage_safe_pct") is None or float(predictive_gate.get("leakage_safe_pct")) < 100:
            missing.append("leakage_safe=100%")

        add(
            "PREDICTIVE",
            pg_status if pg_status in {"PASS", "WARN", "BLOCK"} else "BLOCK",
            pg_score,
            100,
            str(pg_reason),
            missing,
        )

    elif wape is not None:
        # Backward-compatible fallback only when v2.8 schema is not available.
        add(
            "PREDICTIVE", "WARN", 100 - wape, 75,
            f"Existe WAPE maduro={wape:.1f}%, pero falta el contrato v2.8 de snapshots emitidos y control leakage.",
            ["install_v28_predictive_gate"]
        )
    else:
        add(
            "PREDICTIVE", "BLOCK", None, 100,
            "No existen pares forecast→actual maduros defendibles. El mes incompleto no se usa como evidencia predictiva.",
            ["historical_forecast_snapshots", "mature_forecast_actual_pairs", "leakage_control"]
        )

    # L4 — recomendación
    if decision_rows and owner_ratio >= 0.8 and rationale_ratio >= 0.8:
        add("RECOMMENDATION", "PASS", round(min(owner_ratio, rationale_ratio) * 100, 1), 80, "Las recomendaciones tienen owner y racional trazable.", [])
    elif decision_rows:
        add("RECOMMENDATION", "WARN", round(min(owner_ratio, rationale_ratio) * 100, 1), 80, "Existen recomendaciones, pero faltan owners o racionales completos.", ["owner", "rationale"])
    else:
        add("RECOMMENDATION", "BLOCK", 0, 80, "No existe una cola de decisiones accionables.", ["decision_queue"])

    # L5 — economics
    if quantified > 0:
        add("ECONOMIC_DECISION", "PASS", quantified, 1, "Al menos una decisión tiene valor, costo y confianza cuantificados.", [])
    elif partial > 0:
        add("ECONOMIC_DECISION", "WARN", partial, 1, "Hay exposición económica parcial, pero aún faltan variables para ROI.", ["value_to_capture", "action_cost", "measured_confidence"])
    else:
        add("ECONOMIC_DECISION", "BLOCK", 0, 1, "Las decisiones todavía no están cuantificadas económicamente.", ["value_at_risk", "value_to_capture", "action_cost", "expected_roi"])

    # L6 — causalidad exige filas reales, no sólo columnas/nombres.
    if causal["linked_complete_rows"] > 0:
        add(
            "CAUSAL_LEARNING", "PASS", causal["linked_complete_rows"], 1,
            "Existe al menos un experimento con treatment/control/baseline vinculado a un outcome MATURE observado.",
            []
        )
    elif causal["experiment_rows"] > 0 or causal["mature_outcome_rows"] > 0:
        add(
            "CAUSAL_LEARNING", "WARN",
            min(causal["experiment_rows"], causal["mature_outcome_rows"]),
            1,
            "Hay evidencia experimental u outcomes maduros, pero todavía no están vinculados en un ciclo causal completo.",
            ["linked_experiment_outcome"]
        )
    else:
        add(
            "CAUSAL_LEARNING", "BLOCK", 0, 1,
            "No existen filas reales con treatment/control/baseline y outcome MATURE; la presencia de columnas no cuenta como evidencia causal.",
            ["treatment_control_baseline", "mature_realized_outcome"]
        )

    # L7 — closed loop
    causal_pass = any(g["claim_level"] == "CAUSAL_LEARNING" and g["gate_status"] == "PASS" for g in gates)
    econ_pass = any(g["claim_level"] == "ECONOMIC_DECISION" and g["gate_status"] == "PASS" for g in gates)
    if causal_pass and econ_pass:
        add("CLOSED_LOOP", "PASS", 100, 100, "Decisión económica + outcome causal permiten cerrar aprendizaje.", [])
    else:
        add("CLOSED_LOOP", "BLOCK", 0, 100, "Todavía no existe un ciclo probado decisión→acción→outcome→aprendizaje.", ["decision_outcome_feedback_loop"])

    diagnostics = {
        "forecast_evaluation": forecast_eval,
        "causal_evidence": causal,
    }
    return gates, diagnostics


def summarize_gates(gates: list[dict]):
    current_level = 0
    next_gate = None
    for gate in sorted(gates, key=lambda x: x["level_number"]):
        if gate["gate_status"] == "PASS" and gate["level_number"] == current_level + 1:
            current_level += 1
        elif next_gate is None:
            next_gate = gate
            break

    current_label = "Sin gate validado"
    if current_level:
        current_label = next(x[2] for x in LEVELS if x[1] == current_level)

    return {
        "growth_altitude_level": current_level,
        "growth_altitude_label": current_label,
        "next_gate_level": next_gate["claim_level"] if next_gate else None,
        "next_gate_status": next_gate["gate_status"] if next_gate else None,
        "next_gate_reason": next_gate["reason"] if next_gate else "Máxima altitud validada.",
        "pass_count": sum(g["gate_status"] == "PASS" for g in gates),
        "warn_count": sum(g["gate_status"] == "WARN" for g in gates),
        "block_count": sum(g["gate_status"] == "BLOCK" for g in gates),
    }


def decision_outcome_gaps(decision_rows: list[dict]):
    rows = []
    for r in decision_rows:
        missing = [x.strip() for x in str(r.get("missing_evidence") or "").split(",") if x.strip()]
        rows.append({
            "decision_id": r.get("decision_id"),
            "project_key": r.get("project_key"),
            "decision_title": r.get("decision_title"),
            "owner": r.get("owner"),
            "decision_status": r.get("decision_status"),
            "quantification_status": r.get("quantification_status"),
            "value_at_risk": r.get("value_at_risk"),
            "value_to_capture": r.get("value_to_capture"),
            "action_cost": r.get("action_cost"),
            "confidence": r.get("confidence"),
            "expected_roi": r.get("expected_roi"),
            "missing_evidence": ", ".join(missing),
            "outcome_status": "NOT_MEASURED",
            "next_required_step": (
                "Define owner/deadline/metric and capture realized outcome."
                if missing else
                "Measure realized outcome and attribution."
            ),
        })
    return rows


def _write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)



def write_governed_decision_artifacts(root: Path, digest: dict, actions: list[dict], gate_summary: dict):
    """
    The CEO notebook runs before Evidence/Outcome enrichment.
    Therefore its ceo_decision_queue.csv/png are stale by construction.
    This writer intentionally replaces those two CEO artifacts with the
    governed queue produced from PostgreSQL after enrichment.
    """
    if not actions:
        return {"status": "SKIPPED_NO_GOVERNED_ACTIONS"}

    out = root / "artifacts" / "medallio_ceo_briefing"
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for a in actions[:10]:
        value = a.get("value_at_stake_soles")
        value_label = None if value is None else f"S/ {float(value):,.0f}"
        rows.append({
            "project": a.get("project_key"),
            "project_name": a.get("project_name"),
            "decision": a.get("decision"),
            "value_at_stake": value_label or a.get("value_at_stake_type") or "No cuantificado",
            "confidence": a.get("confidence_label"),
            "urgency": a.get("urgency"),
            "owner": a.get("owner"),
            "why": a.get("why"),
            "attention_score": a.get("attention_score"),
            "suggested_outcome_metric": a.get("suggested_outcome_metric"),
            "outcome_required": a.get("outcome_required"),
            "roi_required": a.get("roi_required"),
        })

    pd.DataFrame(rows).to_csv(out / "ceo_decision_queue.csv", index=False)

    # Preserve notebook summary metrics; update only the governed narrative.
    board_path = out / "board_summary.json"
    try:
        board = json.loads(board_path.read_text(encoding="utf-8")) if board_path.exists() else {}
    except Exception:
        board = {}

    board["top_3_decisions"] = [
        {
            "project": r.get("project"),
            "decision": r.get("decision"),
            "value_at_stake": r.get("value_at_stake"),
            "confidence": r.get("confidence"),
            "urgency": r.get("urgency"),
            "owner": r.get("owner"),
            "why": r.get("why"),
        }
        for r in rows[:3]
    ]
    # Keep the portable board artifact consistent with the live email/digest.
    board["forecast_wape_pct"] = (digest.get("summary") or {}).get("forecast_wape_pct")
    board["forecast_bias"] = (digest.get("summary") or {}).get("forecast_bias")

    board["growth_altitude"] = {
        "level": gate_summary.get("growth_altitude_level"),
        "label": gate_summary.get("growth_altitude_label"),
        "next_gate": gate_summary.get("next_gate_level"),
        "next_gate_status": gate_summary.get("next_gate_status"),
    }
    board["governed_queue"] = True
    board_path.write_text(
        json.dumps(board, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # Replace the stale one-bar chart.
    try:
        import matplotlib.pyplot as plt

        chart_rows = rows[:6]
        labels = [
            (
                f"{r.get('project') or 'PORTFOLIO'} · "
                f"{str(r.get('decision') or '')[:55]}"
            )
            for r in chart_rows
        ]
        scores = [
            float(r.get("attention_score") or (100 if r.get("project") == "PORTFOLIO" else 0))
            for r in chart_rows
        ]

        fig, ax = plt.subplots(figsize=(13, 7))
        ax.barh(labels[::-1], scores[::-1])
        ax.set_xlabel("Prioridad ejecutiva / Attention Score")
        ax.set_title("CEO Decision Queue — decisiones gobernadas por evidencia")
        ax.set_xlim(0, max(100, max(scores or [100]) * 1.08))
        for idx, value in enumerate(scores[::-1]):
            ax.text(value + 1, idx, f"{value:.0f}", va="center")
        fig.tight_layout()
        fig.savefig(out / "04_ceo_decision_queue.png", dpi=160)
        plt.close(fig)
    except Exception as exc:
        return {"status": f"CSV_OK_CHART_ERROR:{type(exc).__name__}:{exc}", "rows": len(rows)}

    return {"status": "OK", "rows": len(rows)}


def write_artifacts(root: Path, slot: str, gates, gate_summary, project_states, decisions, outcome_gaps, diagnostics=None):
    out = root / "artifacts" / "medallio_ceo_briefing"
    out.mkdir(parents=True, exist_ok=True)

    _write_csv(out / "evidence_gate_register.csv", gates)
    _write_csv(out / "project_growth_state.csv", project_states)
    _write_csv(out / "decision_ledger_candidate.csv", decisions)
    _write_csv(out / "decision_outcome_gap.csv", outcome_gaps)

    diagnostics = diagnostics or {}

    forecast_eval = diagnostics.get("forecast_evaluation") or {}
    detail_rows = forecast_eval.get("detail_rows") or []
    _write_csv(out / "forecast_evaluation_maturity.csv", detail_rows)

    causal = diagnostics.get("causal_evidence") or {}
    (out / "causal_evidence_status.json").write_text(
        json.dumps(causal, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "slot": slot,
        "gate_summary": gate_summary,
        "gates": gates,
        "top_decisions": decisions[:5],
        "project_count": len(project_states),
        "forecast_evaluation": {
            k: v for k, v in forecast_eval.items() if k != "detail_rows"
        },
        "causal_evidence": causal,
    }
    (out / "evidence_outcome_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _dsn_from_env():
    for key in ["MEDALLIO_DATABASE_URL", "DATABASE_URL", "POSTGRES_DSN", "PG_DSN"]:
        if os.getenv(key):
            return os.getenv(key)
    required = ["PGHOST", "PGDATABASE", "PGUSER"]
    if all(os.getenv(x) for x in required):
        parts = [
            f"host={os.getenv('PGHOST')}",
            f"port={os.getenv('PGPORT', '5432')}",
            f"dbname={os.getenv('PGDATABASE')}",
            f"user={os.getenv('PGUSER')}",
        ]
        if os.getenv("PGPASSWORD"):
            parts.append(f"password={os.getenv('PGPASSWORD')}")
        return " ".join(parts)
    return None


def sync_to_db(root: Path, cfg: dict, run_id: str, gates, project_states, decisions):
    policy = (cfg.get("v27") or {})
    if not policy.get("auto_sync_db", False):
        return {"enabled": False, "status": "SKIPPED"}

    required_relations = [
        "model_control.evidence_gate",
        "analytics.project_growth_state_snapshot",
        "decision_intelligence.decision_ledger",
    ]

    try:
        with medallio_db_connection() as conn:
            with conn.cursor() as cur:
                missing = []
                for rel in required_relations:
                    cur.execute("SELECT to_regclass(%s)", (rel,))
                    if cur.fetchone()[0] is None:
                        missing.append(rel)

                if missing:
                    return {
                        "enabled": True,
                        "status": "SKIPPED_SCHEMA_NOT_INSTALLED",
                        "missing_relations": missing,
                    }

                for g in gates:
                    cur.execute(
                        """
                        INSERT INTO model_control.evidence_gate(
                            gate_id, run_id, gate_ts, slot, claim_level, gate_name,
                            gate_status, score, threshold, reason, missing_evidence
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (gate_id) DO UPDATE SET
                            gate_status=EXCLUDED.gate_status,
                            score=EXCLUDED.score,
                            threshold=EXCLUDED.threshold,
                            reason=EXCLUDED.reason,
                            missing_evidence=EXCLUDED.missing_evidence
                        """,
                        (
                            g["gate_id"], run_id, g["gate_ts"], g["slot"],
                            g["claim_level"], g["gate_name"], g["gate_status"],
                            g["score"], g["threshold"], g["reason"], g["missing_evidence"],
                        ),
                    )

                for ps in project_states:
                    cur.execute(
                        """
                        INSERT INTO analytics.project_growth_state_snapshot(
                            snapshot_ts, slot, project_key, project_name, source_artifact,
                            stock_units, stock_value, sales_units, sales_value,
                            absorption_rate, months_to_zero, avg_price_m2,
                            forecast_units, forecast_wape_pct, target_value, gap_value,
                            value_to_capture, action_cost, uplift_pct, confidence,
                            expected_roi, trust_score_pct, evidence_grade
                        )
                        VALUES (
                            %s,%s,%s,%s,%s,
                            %s,%s,%s,%s,
                            %s,%s,%s,
                            %s,%s,%s,%s,
                            %s,%s,%s,%s,
                            %s,%s,%s
                        )
                        """,
                        (
                            ps.get("snapshot_ts"), ps.get("slot"), ps.get("project_key"),
                            ps.get("project_name"), ps.get("source_artifact"),
                            ps.get("stock_units"), ps.get("stock_value"),
                            ps.get("sales_units"), ps.get("sales_value"),
                            ps.get("absorption_rate"), ps.get("months_to_zero"),
                            ps.get("avg_price_m2"), ps.get("forecast_units"),
                            ps.get("forecast_wape_pct"), ps.get("target_value"),
                            ps.get("gap_value"), ps.get("value_to_capture"),
                            ps.get("action_cost"), ps.get("uplift_pct"),
                            ps.get("confidence"), ps.get("expected_roi"),
                            ps.get("trust_score_pct"), ps.get("evidence_grade"),
                        ),
                    )

                for d in decisions:
                    cur.execute(
                        """
                        INSERT INTO decision_intelligence.decision_ledger(
                            decision_id, run_id, decision_ts, slot, project_key, challenge,
                            decision_title, decision_rationale, owner, deadline, decision_status,
                            decision_level, value_at_risk, economic_exposure, value_to_capture,
                            action_cost, confidence, expected_roi, confidence_adjusted_value,
                            quantification_status, missing_evidence, source_artifact
                        )
                        VALUES (
                            %s,%s,%s,%s,%s,%s,
                            %s,%s,%s,%s,%s,
                            %s,%s,%s,%s,
                            %s,%s,%s,%s,
                            %s,%s,%s
                        )
                        ON CONFLICT (decision_id) DO UPDATE SET
                            owner=EXCLUDED.owner,
                            deadline=EXCLUDED.deadline,
                            decision_status=EXCLUDED.decision_status,
                            value_at_risk=EXCLUDED.value_at_risk,
                            economic_exposure=EXCLUDED.economic_exposure,
                            value_to_capture=EXCLUDED.value_to_capture,
                            action_cost=EXCLUDED.action_cost,
                            confidence=EXCLUDED.confidence,
                            expected_roi=EXCLUDED.expected_roi,
                            confidence_adjusted_value=EXCLUDED.confidence_adjusted_value,
                            quantification_status=EXCLUDED.quantification_status,
                            missing_evidence=EXCLUDED.missing_evidence,
                            updated_at=now()
                        """,
                        (
                            d.get("decision_id"), run_id, d.get("decision_ts"), d.get("slot"),
                            d.get("project_key"), d.get("challenge"), d.get("decision_title"),
                            d.get("decision_rationale"), d.get("owner"), d.get("deadline") or None,
                            d.get("decision_status"), d.get("decision_level"), d.get("value_at_risk"),
                            d.get("economic_exposure"), d.get("value_to_capture"), d.get("action_cost"),
                            d.get("confidence"), d.get("expected_roi"), d.get("confidence_adjusted_value"),
                            d.get("quantification_status"), d.get("missing_evidence"),
                            d.get("source_artifact"),
                        ),
                    )

            conn.commit()

        return {
            "enabled": True,
            "status": "OK",
            "gates_written": len(gates),
            "project_states_written": len(project_states),
            "decisions_written": len(decisions),
        }

    except Exception as exc:
        # Preserve the real failure class/message; do not relabel it as connection failure.
        return {
            "enabled": True,
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def enrich_digest_v27(root: Path, cfg: dict, digest: dict, fresh_files: list[Path], slot: str):
    run_id = f"run_{_hash({'slot': slot, 'ts': datetime.now(timezone.utc).isoformat(), 'headline': digest.get('headline')})}"

    # L2 must be backed by the governed DB contract whenever it exists.
    project_states = load_project_growth_state_from_db(slot)
    state_source = "DB_VIEW"
    if not project_states:
        project_states = discover_project_growth_state(
            fresh_files, digest.get("summary") or {}, slot
        )
        state_source = "ARTIFACT_DISCOVERY"

    # Replace the generic CEO fallback with governed project actions.
    governed_actions = load_ceo_growth_actions_from_db()
    digest = inject_governed_decisions(digest, governed_actions)

    decisions = build_decision_ledger(digest, project_states, slot)

    gates, diagnostics = build_evidence_gates(
        digest, fresh_files, project_states, decisions, slot
    )
    gate_summary = summarize_gates(gates)
    gaps = decision_outcome_gaps(decisions)

    for ps in project_states:
        ps["evidence_grade"] = (
            "A" if gate_summary["growth_altitude_level"] >= 5 else
            "B" if gate_summary["growth_altitude_level"] >= 3 else
            "C"
        )

    write_artifacts(
        root, slot, gates, gate_summary, project_states, decisions, gaps,
        diagnostics=diagnostics,
    )

    visuals = write_calibrated_ceo_visuals(
        root, gates, gate_summary, decisions
    )

    governed_artifacts = write_governed_decision_artifacts(
        root, digest, governed_actions, gate_summary
    )

    db_sync = sync_to_db(root, cfg, run_id, gates, project_states, decisions)

    digest["v27"] = {
        "run_id": run_id,
        "gate_summary": gate_summary,
        "gates": gates,
        "project_growth_state": project_states,
        "project_growth_state_source": state_source,
        "governed_actions": governed_actions,
        "decision_ledger": decisions,
        "decision_outcome_gap": gaps,
        "forecast_evaluation": diagnostics.get("forecast_evaluation"),
        "causal_evidence": diagnostics.get("causal_evidence"),
        "calibrated_visuals": visuals,
        "governed_decision_artifacts": governed_artifacts,
        "db_sync": db_sync,
    }
    return digest
