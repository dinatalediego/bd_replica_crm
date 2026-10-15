from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


VERSION = "2.9.0"

PROJECT_ALIASES = [
    "project_key", "codigo_proyecto", "project", "proyecto",
    "project_code", "codigo", "cod_proyecto"
]

DATE_HINTS = [
    "periodo_mes", "fecha", "date", "created_at", "captured_at",
    "issued_at", "decision_ts", "outcome_ts", "snapshot_ts", "fecha_corte"
]

# Sources are intentionally layered.
# Missing relations do not fail the context compiler.
SOURCES = [
    # Core / business state
    ("analytics.v_project_growth_state", "commercial_state", 20),
    ("analytics.comercial_proyecto_mes", "commercial_history", 36),

    # Product / unit / stock history
    ("analytics.snapshot_unidad_diario", "product_stock", 250),
    ("analytics.historial_oferta_unidad", "product_offer", 250),
    ("features.v_dataset_unidad_entrenamiento", "product_features", 250),

    # Pricing / econometrics
    ("analytics.v_econometria_serie_precios", "pricing", 120),
    ("analytics.v_econometria_cobertura", "econometrics", 60),
    ("features.v_estacionalidad_panel", "seasonality", 60),

    # Predictive factory
    ("analytics.v_forecast_issue_quality_v284", "predictive_issue", 120),
    ("analytics.v_forecast_maturity_clock_v283", "predictive_maturity", 120),
    ("analytics.v_forecast_performance_v283", "predictive_performance", 120),
    ("analytics.v_forecast_performance_by_project_horizon", "predictive_legacy", 120),

    # Decision / outcome loop
    ("decision_intelligence.v_decision_execution_gap_v284", "decision_execution", 100),
    ("decision_intelligence.decision_ledger", "decision_history", 100),
    ("decision_intelligence.v_decision_outcome_status", "decision_outcomes", 100),
]


def jdefault(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if hasattr(v, "item") and callable(getattr(v, "item")):
        try:
            return v.item()
        except Exception:
            pass
    return str(v)


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=jdefault
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def relation_exists(cur, rel: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def relation_columns(cur, rel: str) -> list[str]:
    schema, name = rel.split(".", 1)
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, name),
    )
    return [r[0] for r in cur.fetchall()]


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def qrel(rel: str) -> str:
    schema, name = rel.split(".", 1)
    return f"{qident(schema)}.{qident(name)}"


def pick_project_col(columns: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for alias in PROJECT_ALIASES:
        if alias.lower() in lower:
            return lower[alias.lower()]
    return None


def pick_date_col(columns: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for hint in DATE_HINTS:
        if hint.lower() in lower:
            return lower[hint.lower()]
    # then fuzzy
    for c in columns:
        cl = c.lower()
        if any(h in cl for h in ("fecha", "date", "_at", "periodo")):
            return c
    return None


def fetch_dicts(cur, sql: str, params=None) -> list[dict]:
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_project_universe(cur) -> list[dict]:
    if relation_exists(cur, "analytics.v_project_growth_state"):
        cols = relation_columns(cur, "analytics.v_project_growth_state")
        pcol = pick_project_col(cols)
        if pcol:
            rows = fetch_dicts(
                cur,
                f"SELECT * FROM analytics.v_project_growth_state "
                f"ORDER BY {qident(pcol)}"
            )
            out = []
            for r in rows:
                pk = r.get(pcol)
                if pk is None:
                    continue
                name = (
                    r.get("project_name")
                    or r.get("nombre_proyecto")
                    or r.get("project")
                    or str(pk)
                )
                out.append({
                    "project_key": str(pk),
                    "project_name": str(name) if name is not None else str(pk),
                    "growth_state": r,
                })
            if out:
                return out

    # fallback
    if relation_exists(cur, "analytics.comercial_proyecto_mes"):
        cols = relation_columns(cur, "analytics.comercial_proyecto_mes")
        pcol = pick_project_col(cols)
        if pcol:
            rows = fetch_dicts(
                cur,
                f"SELECT DISTINCT {qident(pcol)} AS project_key "
                f"FROM analytics.comercial_proyecto_mes "
                f"WHERE {qident(pcol)} IS NOT NULL ORDER BY 1"
            )
            return [
                {
                    "project_key": str(r["project_key"]),
                    "project_name": str(r["project_key"]),
                    "growth_state": {},
                }
                for r in rows
            ]

    return []


def query_project_source(cur, rel: str, project_key: str, limit: int) -> dict:
    if not relation_exists(cur, rel):
        return {
            "relation": rel,
            "status": "MISSING",
            "rows": [],
            "columns": [],
        }

    cols = relation_columns(cur, rel)
    pcol = pick_project_col(cols)
    if not pcol:
        return {
            "relation": rel,
            "status": "NO_PROJECT_KEY",
            "rows": [],
            "columns": cols,
        }

    dcol = pick_date_col(cols)
    order = f" ORDER BY {qident(dcol)} DESC NULLS LAST" if dcol else ""
    sql = (
        f"SELECT * FROM {qrel(rel)} "
        f"WHERE {qident(pcol)}::text = %s"
        f"{order} LIMIT {int(limit)}"
    )
    try:
        rows = fetch_dicts(cur, sql, (str(project_key),))
        return {
            "relation": rel,
            "status": "OK",
            "project_column": pcol,
            "date_column": dcol,
            "rows": rows,
            "columns": cols,
        }
    except Exception as exc:
        return {
            "relation": rel,
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "rows": [],
            "columns": cols,
        }


def numeric(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def compact_rows(rows: list[dict], max_rows=12) -> list[dict]:
    if len(rows) <= max_rows:
        return rows
    # keep newest and oldest evidence without flooding AI context
    head = rows[: max_rows // 2]
    tail = rows[-(max_rows - len(head)):]
    return head + tail


def profile_rows(rows: list[dict]) -> dict:
    if not rows:
        return {
            "row_count": 0,
            "numeric_profile": {},
            "categorical_profile": {},
        }

    keys = []
    seen = set()
    for r in rows[:50]:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)

    numeric_profile = {}
    categorical_profile = {}

    for k in keys[:80]:
        vals = [r.get(k) for r in rows if r.get(k) is not None]
        nums = [numeric(v) for v in vals]
        nums = [x for x in nums if x is not None]

        if nums and len(nums) >= max(2, int(len(vals) * 0.7)):
            try:
                numeric_profile[k] = {
                    "n": len(nums),
                    "min": min(nums),
                    "mean": sum(nums) / len(nums),
                    "median": statistics.median(nums),
                    "max": max(nums),
                }
            except Exception:
                pass
        elif vals:
            text_vals = [str(v) for v in vals]
            counts = Counter(text_vals)
            categorical_profile[k] = {
                "n": len(text_vals),
                "distinct": len(counts),
                "top": counts.most_common(5),
            }

    return {
        "row_count": len(rows),
        "numeric_profile": numeric_profile,
        "categorical_profile": categorical_profile,
    }


def percentile_rank(values: list[float], value: float | None) -> float | None:
    if value is None or not values:
        return None
    clean = sorted(x for x in values if x is not None)
    if not clean:
        return None
    le = sum(1 for x in clean if x <= value)
    return round(100.0 * le / len(clean), 1)


def growth_metric(row: dict, names: list[str]):
    for n in names:
        if n in row and row[n] is not None:
            return numeric(row[n])
    return None


def build_portfolio_reference(projects: list[dict]) -> dict:
    metric_aliases = {
        "stock_units": ["stock_units", "stock", "stock_final"],
        "sales_units": ["last_complete_sales_units", "sales_units", "ventas_mes"],
        "months_to_zero": ["months_to_zero", "meses_stock"],
        "gap_value": ["gap_value", "gap_meta"],
        "attention_score": ["attention_score"],
        "target_value": ["target_value", "meta_valor"],
    }

    all_values = {m: [] for m in metric_aliases}
    per_project = {}

    for p in projects:
        gs = p.get("growth_state") or {}
        vals = {}
        for m, aliases in metric_aliases.items():
            v = growth_metric(gs, aliases)
            vals[m] = v
            if v is not None:
                all_values[m].append(v)
        per_project[p["project_key"]] = vals

    ranks = {}
    for pk, vals in per_project.items():
        ranks[pk] = {}
        for m, v in vals.items():
            ranks[pk][m] = {
                "value": v,
                "percentile": percentile_rank(all_values[m], v),
            }

    return {
        "metric_distribution": {
            m: {
                "n": len(vals),
                "median": statistics.median(vals) if vals else None,
                "mean": sum(vals) / len(vals) if vals else None,
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
            }
            for m, vals in all_values.items()
        },
        "project_ranks": ranks,
    }


def predictive_summary(source_payloads: dict) -> dict:
    issue_rows = source_payloads.get("predictive_issue", {}).get("rows", [])
    maturity_rows = source_payloads.get("predictive_maturity", {}).get("rows", [])
    perf_rows = source_payloads.get("predictive_performance", {}).get("rows", [])
    if not perf_rows:
        perf_rows = source_payloads.get("predictive_legacy", {}).get("rows", [])

    return {
        "issues": len(issue_rows),
        "maturity_status": Counter(
            str(r.get("maturity_status")) for r in maturity_rows
            if r.get("maturity_status") is not None
        ),
        "next_maturity": min(
            [
                str(r.get("expected_maturity_date"))
                for r in maturity_rows
                if r.get("expected_maturity_date") is not None
                and str(r.get("maturity_status")) == "INCUBATING"
            ],
            default=None,
        ),
        "performance_rows": len(perf_rows),
        "performance": compact_rows(perf_rows, 12),
    }


def decision_summary(source_payloads: dict) -> dict:
    execution = source_payloads.get("decision_execution", {}).get("rows", [])
    history = source_payloads.get("decision_history", {}).get("rows", [])
    outcomes = source_payloads.get("decision_outcomes", {}).get("rows", [])

    # v_decision_outcome_status may contain one status row per decision even
    # when the decision has NO outcome. Do not confuse "status row exists"
    # with "an outcome has been observed".
    actual_outcome_count = 0
    mature_outcome_count = 0
    for r in outcomes:
        try:
            actual_outcome_count += int(r.get("outcome_count") or 0)
        except Exception:
            pass
        try:
            mature_outcome_count += int(r.get("mature_outcome_count") or 0)
        except Exception:
            pass

    return {
        "execution_statuses": Counter(
            str(r.get("execution_status")) for r in execution
            if r.get("execution_status") is not None
        ),
        "latest_execution": execution[:5],
        "decision_history_count": len(history),
        "recent_decisions": history[:8],
        "outcome_status_rows": len(outcomes),
        "actual_outcome_count": actual_outcome_count,
        "mature_outcome_count": mature_outcome_count,
        # kept for backwards readability; this is NOT used as proof of outcome
        "outcome_records": len(outcomes),
        "recent_outcomes": outcomes[:8],
    }


def evidence_claim_level(source_payloads: dict) -> tuple[str, str]:
    pred = predictive_summary(source_payloads)
    dec = decision_summary(source_payloads)

    matured = 0
    for k, v in pred["maturity_status"].items():
        if k == "EVALUATED":
            matured += int(v)

    # Strict evidence ceiling:
    # A status row saying NO_OUTCOME is not an outcome.
    has_actual_outcome = int(dec.get("actual_outcome_count") or 0) > 0

    if has_actual_outcome:
        return (
            "OUTCOME",
            "Existen outcomes realmente registrados; causalidad no se presume sin diseño de identificación."
        )
    if matured > 0:
        return (
            "PREDICTIVE",
            "Existen outcomes predictivos maduros; no convertir precisión en causalidad."
        )
    if pred["issues"] > 0:
        return (
            "PREDICTIVE_INCUBATING",
            "Hay forecasts prospectivos, pero todavía pueden estar incubando."
        )
    return (
        "DIAGNOSTIC",
        "El contexto soporta diagnóstico; no elevar claims predictivos sin evidencia prospectiva."
    )


def deterministic_hypotheses(core: dict, ranks: dict, source_payloads: dict) -> list[dict]:
    out = []

    gap = ranks.get("gap_value", {}).get("value")
    gap_pct = ranks.get("gap_value", {}).get("percentile")
    months = ranks.get("months_to_zero", {}).get("value")
    months_pct = ranks.get("months_to_zero", {}).get("percentile")
    stock = ranks.get("stock_units", {}).get("value")
    att = ranks.get("attention_score", {}).get("value")

    if gap is not None and gap_pct is not None and gap_pct >= 75:
        out.append({
            "type": "ECONOMIC_EXPOSURE",
            "evidence": f"gap_value está en percentil {gap_pct} del portafolio",
            "question": "¿Qué palancas explican el gap y cuáles tienen mayor Value to Capture ajustado por costo y confianza?",
        })

    if months is not None and months_pct is not None and months_pct >= 75:
        out.append({
            "type": "ABSORPTION_RISK",
            "evidence": f"months_to_zero={months:.1f}, percentil {months_pct}",
            "question": "¿La cobertura elevada proviene de mix, precio, estacionalidad, etapa o baja demanda relativa?",
        })

    if stock is not None and stock > 0:
        out.append({
            "type": "UNIT_MIX",
            "evidence": f"stock_units observado={stock:.0f}",
            "question": "¿Qué dormitorios/tipologías concentran stock, tiempo de exposición y sensibilidad de precio?",
        })

    pred = predictive_summary(source_payloads)
    if pred["issues"] > 0 and pred["next_maturity"]:
        out.append({
            "type": "PREDICTIVE_EVIDENCE",
            "evidence": f"{pred['issues']} registros predictivos; próxima madurez {pred['next_maturity']}",
            "question": "¿Qué horizontes/modelos ganan al benchmark naïve cuando maduren los outcomes?",
        })

    dec = decision_summary(source_payloads)
    if dec["latest_execution"]:
        status = dec["latest_execution"][0].get("execution_status")
        if status and status not in ("LEARNING_COMPLETE",):
            out.append({
                "type": "EXECUTION_GAP",
                "evidence": f"execution_status={status}",
                "question": "¿Qué owner, deadline, acción, baseline u outcome falta para convertir recomendación en aprendizaje?",
            })

    if not out:
        out.append({
            "type": "DISCOVERY",
            "evidence": "No se detectó una señal dominante con las reglas determinísticas.",
            "question": "¿Qué cambió recientemente frente a su propia historia y frente al portafolio?",
        })

    return out[:8]


def layer_readiness(source_payloads: dict) -> dict:
    def ready(*layers):
        return any(
            source_payloads.get(layer, {}).get("status") == "OK"
            and len(source_payloads.get(layer, {}).get("rows", [])) > 0
            for layer in layers
        )

    return {
        "commercial": ready("commercial_state", "commercial_history"),
        "product": ready("product_stock", "product_offer", "product_features"),
        "pricing": ready("pricing", "econometrics"),
        "predictive": ready("predictive_issue", "predictive_maturity", "predictive_performance", "predictive_legacy"),
        "decision": ready("decision_execution", "decision_history"),
        "outcome": ready("decision_outcomes"),
    }


def build_project_context(project: dict, portfolio_ref: dict, source_payloads: dict) -> dict:
    pk = project["project_key"]
    growth = project.get("growth_state") or {}
    ranks = portfolio_ref["project_ranks"].get(pk, {})
    readiness = layer_readiness(source_payloads)
    highest_claim, evidence_warning = evidence_claim_level(source_payloads)

    source_coverage = []
    for layer, payload in source_payloads.items():
        source_coverage.append({
            "layer": layer,
            "relation": payload.get("relation"),
            "status": payload.get("status"),
            "rows": len(payload.get("rows", [])),
            "error": payload.get("error"),
        })

    available = sum(1 for x in source_coverage if x["status"] not in ("MISSING",))
    used = sum(1 for x in source_coverage if x["status"] == "OK" and x["rows"] > 0)

    # core context: source profiles + compact evidence
    sources = {}
    for layer, payload in source_payloads.items():
        rows = payload.get("rows", [])
        sources[layer] = {
            "relation": payload.get("relation"),
            "status": payload.get("status"),
            "row_count": len(rows),
            "profile": profile_rows(rows),
            "sample": compact_rows(rows, 12),
        }

    context = {
        "meta": {
            "context_version": VERSION,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "project_key": pk,
            "project_name": project.get("project_name"),
        },
        "governance": {
            "highest_claim_level": highest_claim,
            "evidence_warning": evidence_warning,
            "rule": "AI must distinguish OBSERVED / DERIVED / PREDICTIVE / RECOMMENDED / OUTCOME and never promote causal claims without identification evidence.",
        },
        "executive_state": growth,
        "portfolio_comparison": ranks,
        "portfolio_reference": portfolio_ref["metric_distribution"],
        "predictive_context": predictive_summary(source_payloads),
        "decision_context": decision_summary(source_payloads),
        "layer_readiness": readiness,
        "source_coverage": source_coverage,
        "sources": sources,
        "ai_hypotheses": deterministic_hypotheses(growth, ranks, source_payloads),
    }

    completeness = round(
        100.0 * sum(1 for v in readiness.values() if v) / len(readiness),
        1
    )

    return {
        "context": context,
        "summary": {
            "project_key": pk,
            "project_name": project.get("project_name"),
            "context_completeness_pct": completeness,
            "source_relations_available": available,
            "source_relations_used": used,
            **{f"{k}_context_ready": v for k, v in readiness.items()},
            "highest_claim_level": highest_claim,
            "evidence_warning": evidence_warning,
        }
    }


def install_schema(root: Path, conn):
    p = root / "sql" / "108_project_intelligence_context" / "01_project_context.sql"
    with conn.cursor() as cur:
        cur.execute(p.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def persist_context(cur, project_context: dict) -> bool:
    c = project_context["context"]
    s = project_context["summary"]
    h = stable_hash(c)

    data_as_of = None
    ch = c.get("sources", {}).get("commercial_history", {})
    samples = ch.get("sample") or []
    for row in samples:
        for key in ("periodo_mes", "fecha_corte", "fecha", "date"):
            if row.get(key) is not None:
                try:
                    data_as_of = str(row.get(key))[:10]
                    break
                except Exception:
                    pass
        if data_as_of:
            break

    cur.execute(
        """
        INSERT INTO analytics.project_context_snapshot_v290(
            context_hash,
            project_key,
            project_name,
            data_as_of,
            context_completeness_pct,
            source_relations_available,
            source_relations_used,
            commercial_context_ready,
            product_context_ready,
            pricing_context_ready,
            predictive_context_ready,
            decision_context_ready,
            outcome_context_ready,
            highest_claim_level,
            evidence_warning,
            context_json
        )
        VALUES(
            %s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s::jsonb
        )
        ON CONFLICT(project_key, context_hash) DO NOTHING
        """,
        (
            h,
            s["project_key"],
            s["project_name"],
            data_as_of,
            s["context_completeness_pct"],
            s["source_relations_available"],
            s["source_relations_used"],
            s["commercial_context_ready"],
            s["product_context_ready"],
            s["pricing_context_ready"],
            s["predictive_context_ready"],
            s["decision_context_ready"],
            s["outcome_context_ready"],
            s["highest_claim_level"],
            s["evidence_warning"],
            json.dumps(c, ensure_ascii=False, default=jdefault),
        ),
    )
    return cur.rowcount > 0


def md_escape(v):
    if v is None:
        return "N/A"
    return str(v).replace("|", "\\|")


def build_markdown(project_context: dict) -> str:
    c = project_context["context"]
    s = project_context["summary"]
    meta = c["meta"]
    lines = [
        f"# {meta['project_name']} ({meta['project_key']}) — Project Intelligence Profile",
        "",
        f"**Medallio Context Version:** {VERSION}  ",
        f"**Context completeness:** {s['context_completeness_pct']}%  ",
        f"**Highest defensible claim:** {s['highest_claim_level']}  ",
        "",
        f"> {s['evidence_warning']}",
        "",
        "## 1. Executive state",
        "",
        "```json",
        json.dumps(c["executive_state"], ensure_ascii=False, indent=2, default=jdefault),
        "```",
        "",
        "## 2. Portfolio position",
        "",
        "| Metric | Value | Percentile |",
        "|---|---:|---:|",
    ]
    for metric, info in c["portfolio_comparison"].items():
        lines.append(
            f"| {metric} | {md_escape(info.get('value'))} | "
            f"{md_escape(info.get('percentile'))}% |"
        )

    lines += [
        "",
        "## 3. Predictive evidence",
        "",
        "```json",
        json.dumps(c["predictive_context"], ensure_ascii=False, indent=2, default=jdefault),
        "```",
        "",
        "## 4. Decision / action / outcome loop",
        "",
        "```json",
        json.dumps(c["decision_context"], ensure_ascii=False, indent=2, default=jdefault),
        "```",
        "",
        "## 5. AI hypotheses to investigate",
        "",
    ]
    for i, h in enumerate(c["ai_hypotheses"], 1):
        lines += [
            f"### {i}. {h['type']}",
            f"- Evidence: {h['evidence']}",
            f"- Question: {h['question']}",
            "",
        ]

    lines += [
        "## 6. Context layer readiness",
        "",
        "| Layer | Ready |",
        "|---|---|",
    ]
    for k, v in c["layer_readiness"].items():
        lines.append(f"| {k} | {'YES' if v else 'NO'} |")

    lines += [
        "",
        "## 7. Governance rule for AI",
        "",
        c["governance"]["rule"],
        "",
        "The detailed structured evidence is stored in `context.json`.",
    ]
    return "\n".join(lines) + "\n"


def build_ai_prompt(project_context: dict) -> str:
    c = project_context["context"]
    return f"""# Medallio AI Project Analyst Prompt

You are the governed project analyst for Medallio.

PROJECT
- key: {c['meta']['project_key']}
- name: {c['meta']['project_name']}

NON-NEGOTIABLE EVIDENCE RULE
{c['governance']['rule']}

CURRENT EVIDENCE CEILING
- highest_claim_level: {c['governance']['highest_claim_level']}
- warning: {c['governance']['evidence_warning']}

TASK
Produce an executive project analysis using ONLY `context.json`.

Required structure:
1. Executive situation — 5 bullets maximum.
2. What changed / what matters now.
3. Portfolio-relative position.
4. Commercial and stock diagnosis.
5. Product / unit-mix questions.
6. Pricing / econometric questions.
7. Predictive evidence and what cannot yet be claimed.
8. Decision execution state.
9. Top 3 hypotheses to test.
10. Top 3 decisions or analyses to prioritize.
11. Evidence gaps that block stronger conclusions.
12. "What would change my mind?" — evidence needed.

Every substantive sentence must begin with one of:
[OBSERVED] [DERIVED] [PREDICTIVE] [RECOMMENDED] [OUTCOME]

Never label a backtest as a prospectively issued forecast.
Never claim causality from correlations, forecasts, or before/after movement alone.
Never invent missing price, customer, unit, action, outcome, deadline, or ROI data.
"""


def export_project(root: Path, project_context: dict):
    c = project_context["context"]
    pk = c["meta"]["project_key"]
    out = root / "artifacts" / "project_intelligence_v290" / pk
    out.mkdir(parents=True, exist_ok=True)

    (out / "context.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2, default=jdefault),
        encoding="utf-8",
    )
    (out / "brief.md").write_text(
        build_markdown(project_context),
        encoding="utf-8",
    )
    (out / "ai_prompt.md").write_text(
        build_ai_prompt(project_context),
        encoding="utf-8",
    )

    coverage = c["source_coverage"]
    if coverage:
        with (out / "source_coverage.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(coverage[0].keys()))
            w.writeheader()
            w.writerows(coverage)


def export_portfolio(root: Path, contexts: list[dict]):
    out = root / "artifacts" / "project_intelligence_v290"
    out.mkdir(parents=True, exist_ok=True)

    rows = [x["summary"] for x in contexts]
    if rows:
        with (out / "portfolio_project_context_index.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    manifest = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects": len(contexts),
        "project_keys": [x["summary"]["project_key"] for x in contexts],
        "average_context_completeness_pct": (
            round(
                sum(x["summary"]["context_completeness_pct"] for x in contexts)
                / len(contexts),
                1,
            )
            if contexts else None
        ),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        import matplotlib.pyplot as plt

        ordered = sorted(
            rows,
            key=lambda r: r["context_completeness_pct"],
        )
        labels = [r["project_key"] for r in ordered]
        vals = [float(r["context_completeness_pct"]) for r in ordered]

        fig, ax = plt.subplots(figsize=(11, 7))
        ax.barh(labels, vals)
        ax.set_title("Project Intelligence — cobertura de contexto por proyecto")
        ax.set_xlabel("% de capas de contexto disponibles")
        ax.set_xlim(0, 100)
        for i, v in enumerate(vals):
            ax.text(v + 1, i, f"{v:.0f}%", va="center")
        fig.tight_layout()
        fig.savefig(out / "project_context_coverage.png", dpi=160)
        plt.close(fig)
    except Exception:
        pass


def compile_all(root: Path, conn, only_project: str | None = None):
    with conn.cursor() as cur:
        projects = get_project_universe(cur)
        if only_project:
            projects = [
                p for p in projects
                if p["project_key"].upper() == only_project.upper()
            ]

        portfolio_ref = build_portfolio_reference(projects if not only_project else get_project_universe(cur))
        compiled = []

        for project in projects:
            source_payloads = {}
            for rel, layer, limit in SOURCES:
                payload = query_project_source(
                    cur, rel, project["project_key"], limit
                )
                payload["relation"] = rel
                source_payloads[layer] = payload

            pc = build_project_context(project, portfolio_ref, source_payloads)
            inserted = persist_context(cur, pc)
            pc["summary"]["persisted_new_snapshot"] = inserted
            export_project(root, pc)
            compiled.append(pc)

        conn.commit()

    export_portfolio(root, compiled)
    return compiled


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        choices=["install", "refresh", "status", "all"],
        default="status",
    )
    parser.add_argument("--project", default=None)
    args = parser.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command in ("install", "all"):
            install_schema(root, conn)
            print("[V2.9.0] schema: OK")

        if args.command in ("refresh", "all"):
            contexts = compile_all(root, conn, args.project)
            print(f"[V2.9.0] compiled_projects={len(contexts)}")
            for x in contexts:
                s = x["summary"]
                print(
                    f"  {s['project_key']} | context={s['context_completeness_pct']}% | "
                    f"claim={s['highest_claim_level']} | "
                    f"sources={s['source_relations_used']}/{s['source_relations_available']} | "
                    f"new_snapshot={s.get('persisted_new_snapshot')}"
                )

        if args.command == "status":
            with conn.cursor() as cur:
                if not relation_exists(cur, "analytics.v_project_context_latest_v290"):
                    print("[V2.9.0] schema not installed.")
                    return
                rows = fetch_dicts(
                    cur,
                    """
                    SELECT
                        project_key, project_name,
                        context_completeness_pct,
                        source_relations_used,
                        highest_claim_level,
                        captured_at
                    FROM analytics.v_project_context_latest_v290
                    ORDER BY context_completeness_pct DESC, project_key
                    """
                )
            print(f"[V2.9.0] project_contexts={len(rows)}")
            for r in rows:
                print(
                    f"  {r['project_key']} | "
                    f"context={r['context_completeness_pct']}% | "
                    f"claim={r['highest_claim_level']} | "
                    f"sources={r['source_relations_used']} | "
                    f"captured={r['captured_at']}"
                )


if __name__ == "__main__":
    main()
