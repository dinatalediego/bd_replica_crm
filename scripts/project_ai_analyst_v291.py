from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


VERSION = "2.9.1"


def jd(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=jd).encode("utf-8")
    ).hexdigest()


def relation_exists(cur, rel: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def fetch_dicts(cur, sql: str, params=None):
    cur.execute(sql, params or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def install_schema(root: Path, conn):
    p = root / "sql" / "109_ai_project_analyst" / "01_ai_project_analyst.sql"
    with conn.cursor() as cur:
        cur.execute(p.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def active_keys(root: Path) -> list[str]:
    p = root / "config" / "active_portfolio_v291.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("active_portfolio", [])


def num(v):
    try:
        if v is None:
            return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def get_percentile(ctx: dict, metric: str):
    return num((ctx.get("portfolio_comparison") or {}).get(metric, {}).get("percentile"))


def exec_status(ctx: dict) -> str:
    statuses = (ctx.get("decision_context") or {}).get("execution_statuses") or {}
    if isinstance(statuses, dict) and statuses:
        return sorted(statuses, key=lambda k: (-int(statuses[k]), k))[0]
    return "NO_GOVERNED_DECISION"


def predictive_state(ctx: dict) -> str:
    pred = ctx.get("predictive_context") or {}
    issues = int(pred.get("issues") or 0)
    maturity = pred.get("maturity_status") or {}
    if maturity.get("EVALUATED"):
        return "EVALUATED"
    if issues > 0:
        return "INCUBATING"
    return "NO_PROSPECTIVE_EVIDENCE"


def effective_evidence_level(ctx: dict, stored_level: str | None = None) -> str:
    """
    Recompute the evidence ceiling from the payload itself.
    Protects v2.9.1 from stale v2.9.0 snapshots where a NO_OUTCOME status row
    could previously be mistaken for a real observed outcome.
    """
    dec = ctx.get("decision_context") or {}
    recent = dec.get("recent_outcomes") or []

    actual_outcomes = dec.get("actual_outcome_count")
    if actual_outcomes is None:
        actual_outcomes = 0
        for r in recent:
            try:
                actual_outcomes += int(r.get("outcome_count") or 0)
            except Exception:
                pass

    if int(actual_outcomes or 0) > 0:
        return "OUTCOME"

    pred = ctx.get("predictive_context") or {}
    maturity = pred.get("maturity_status") or {}
    if int(maturity.get("EVALUATED") or 0) > 0:
        return "PREDICTIVE"

    if int(pred.get("issues") or 0) > 0:
        return "PREDICTIVE_INCUBATING"

    return "DIAGNOSTIC"


def economic_signal(ctx: dict) -> str:
    ex = ctx.get("executive_state") or {}
    econ = str(ex.get("economics_conciliacion") or "")
    gap = num(ex.get("gap_value"))
    cumplimiento = num(ex.get("cumplimiento_actual"))
    if econ and econ != "OK":
        return "RECONCILIATION_REQUIRED"
    if gap is not None and gap <= 0:
        return "TARGET_MET_OR_EXCEEDED"
    if cumplimiento is not None and cumplimiento >= 0.95:
        return "NEAR_TARGET"
    if gap is not None and gap >= 20_000_000:
        return "HIGH_VALUE_GAP"
    return "NORMAL"


def derive_archetype(ctx: dict) -> str:
    ex = ctx.get("executive_state") or {}
    econ = str(ex.get("economics_conciliacion") or "")
    execution = exec_status(ctx)
    pred = predictive_state(ctx)

    stock = num(ex.get("stock_units")) or 0
    gap = num(ex.get("gap_value")) or 0
    cumplimiento = num(ex.get("cumplimiento_actual"))
    months = num(ex.get("months_to_zero"))
    gap_pct = get_percentile(ctx, "gap_value")
    stock_pct = get_percentile(ctx, "stock_units")

    if econ and econ != "OK":
        return "DATA_RECONCILIATION"

    if execution in {
        "NEEDS_DEADLINE", "NEEDS_ACTION", "ACTION_IN_PROGRESS",
        "WAITING_OUTCOME", "OUTCOME_IMMATURE"
    }:
        return "EXECUTION_CONTRACT"

    if cumplimiento is not None and cumplimiento >= 1.0:
        return "CLOSEOUT_LEARNING"

    if stock <= 10 and cumplimiento is not None and cumplimiento >= 0.95:
        return "CLOSEOUT_OPTIMIZATION"

    if pred == "NO_PROSPECTIVE_EVIDENCE" and (
        (stock_pct or 0) >= 70 or (months or 0) >= 12
    ):
        return "DIAGNOSTIC_TO_PREDICTIVE"

    if (gap_pct or 0) >= 75 and (stock_pct or 0) >= 75:
        return "VALUE_CAPTURE_DESIGN"

    if months is not None and months >= 15:
        return "ABSORPTION_DIAGNOSIS"

    if gap > 0:
        return "PORTFOLIO_OPTIMIZATION"

    return "MONITOR"


def priority_score(ctx: dict, archetype: str) -> float:
    ex = ctx.get("executive_state") or {}

    gap_pct = get_percentile(ctx, "gap_value") or 0
    stock_pct = get_percentile(ctx, "stock_units") or 0
    months_pct = get_percentile(ctx, "months_to_zero") or 0
    att_pct = get_percentile(ctx, "attention_score") or 0

    score = (
        0.30 * gap_pct
        + 0.25 * stock_pct
        + 0.20 * months_pct
        + 0.15 * att_pct
    )

    if archetype == "EXECUTION_CONTRACT":
        score += 10
    elif archetype == "DATA_RECONCILIATION":
        score += 8
    elif archetype == "VALUE_CAPTURE_DESIGN":
        score += 7
    elif archetype == "DIAGNOSTIC_TO_PREDICTIVE":
        score += 5

    # Avoid over-prioritizing projects that have already met the value target.
    cumplimiento = num(ex.get("cumplimiento_actual"))
    if cumplimiento is not None and cumplimiento >= 1.0:
        score -= 25
    elif cumplimiento is not None and cumplimiento >= 0.95:
        score -= 12

    return round(max(0, min(100, score)), 1)


def contract_type(archetype: str) -> str:
    return {
        "EXECUTION_CONTRACT": "EXECUTION_EXPERIMENT",
        "DATA_RECONCILIATION": "DATA_RECONCILIATION",
        "VALUE_CAPTURE_DESIGN": "ECONOMIC_VALUE_CAPTURE",
        "ABSORPTION_DIAGNOSIS": "ABSORPTION_DIAGNOSIS",
        "DIAGNOSTIC_TO_PREDICTIVE": "EVIDENCE_COVERAGE_PLAN",
        "CLOSEOUT_OPTIMIZATION": "CLOSEOUT_PLAN",
        "CLOSEOUT_LEARNING": "CLOSEOUT_LEARNING_REVIEW",
        "PORTFOLIO_OPTIMIZATION": "PORTFOLIO_OPTIMIZATION",
        "MONITOR": "MONITORING_PLAN",
    }.get(archetype, "ANALYSIS_PLAN")


def hypothesis_for(ctx: dict, archetype: str) -> str:
    ex = ctx.get("executive_state") or {}
    name = ctx.get("meta", {}).get("project_name")
    gap = num(ex.get("gap_value"))
    months = num(ex.get("months_to_zero"))
    stock = num(ex.get("stock_units"))

    if archetype == "EXECUTION_CONTRACT":
        return (
            f"{name}: una intervención definida ex ante puede mejorar la métrica primaria "
            "frente a su baseline, pero debe capturarse costo, deadline, outcome y ROI."
        )
    if archetype == "DATA_RECONCILIATION":
        return (
            f"{name}: antes de decidir con valor económico, la conciliación de meta, colocado "
            "y stock debe quedar resuelta y reproducible."
        )
    if archetype == "VALUE_CAPTURE_DESIGN":
        return (
            f"{name}: la combinación de gap económico y stock relativo justifica cuantificar "
            "Value to Capture antes de seleccionar una intervención."
        )
    if archetype == "ABSORPTION_DIAGNOSIS":
        return (
            f"{name}: la cobertura de stock elevada puede estar explicada por mix, precio, "
            "estacionalidad o demanda; separar mecanismos antes de intervenir."
        )
    if archetype == "DIAGNOSTIC_TO_PREDICTIVE":
        return (
            f"{name}: el diagnóstico comercial es suficiente para priorizar preguntas, pero "
            "falta evidencia prospectiva para usar forecast en una decisión."
        )
    if archetype == "CLOSEOUT_OPTIMIZATION":
        return (
            f"{name}: con stock bajo y meta casi alcanzada, el problema es optimizar cierre "
            "y margen, no maximizar volumen a cualquier costo."
        )
    if archetype == "CLOSEOUT_LEARNING":
        return (
            f"{name}: el proyecto debe usarse como caso de cierre para extraer aprendizaje "
            "transferible a futuros proyectos."
        )
    return (
        f"{name}: el próximo análisis debe maximizar información útil antes de comprometer "
        "una intervención económica."
    )


def proposed_action(ctx: dict, archetype: str) -> str:
    ex = ctx.get("executive_state") or {}
    existing = ex.get("suggested_action")

    if archetype == "EXECUTION_CONTRACT" and existing:
        return existing
    if archetype == "DATA_RECONCILIATION":
        return "Conciliar meta, colocado, stock y valor económico; documentar una única fuente de verdad antes de escalar decisión."
    if archetype == "VALUE_CAPTURE_DESIGN":
        return "Cuantificar Value to Capture por palanca y diseñar un shortlist de intervenciones comparables con costo, baseline y outcome requerido."
    if archetype == "ABSORPTION_DIAGNOSIS":
        return "Descomponer riesgo de absorción por tipología, precio relativo, etapa y estacionalidad antes de recomendar pricing o campaña."
    if archetype == "DIAGNOSTIC_TO_PREDICTIVE":
        return "Cerrar cobertura prospectiva del forecast y, en paralelo, completar diagnóstico por mix/stock/precio."
    if archetype == "CLOSEOUT_OPTIMIZATION":
        return "Diseñar plan de cierre de stock con protección de margen y foco unidad/tipología, evitando descuentos generalizados."
    if archetype == "CLOSEOUT_LEARNING":
        return "Cerrar excepciones de calidad y documentar qué factores explicaron el desempeño del proyecto para reutilizar aprendizaje."
    return existing or "Mantener monitoreo y formular una intervención sólo si aparece una señal material y medible."


def metric_candidates(ctx: dict, archetype: str):
    ex = ctx.get("executive_state") or {}
    suggested = ex.get("suggested_outcome_metric")
    if suggested:
        primary = str(suggested).split(",")[0].strip()
        secondary = [x.strip() for x in str(suggested).split(",")[1:]]
        return primary, secondary

    if archetype in ("DATA_RECONCILIATION",):
        return "economics_conciliacion", ["gap_value", "commercial_placed_value", "stock_value"]
    if archetype in ("CLOSEOUT_OPTIMIZATION", "CLOSEOUT_LEARNING"):
        return "stock_units", ["months_to_zero", "commercial_placed_value"]
    if archetype in ("DIAGNOSTIC_TO_PREDICTIVE",):
        return "predictive_evidence_coverage", ["forecast_mature_pairs", "forecast_wape_pct"]
    return "absorcion_promedio_3m", ["months_to_zero", "gap_value"]


def required_before_execution(ctx: dict, archetype: str):
    req = [
        "Human owner confirmed",
        "Deadline explicitly approved",
        "Primary metric fixed ex ante",
        "Baseline frozen before action",
        "Success criterion fixed ex ante",
    ]
    if archetype not in ("DATA_RECONCILIATION", "DIAGNOSTIC_TO_PREDICTIVE"):
        req += [
            "Action cost estimated",
            "Outcome capture method defined",
            "ROI measurement plan defined",
        ]
    if archetype == "DATA_RECONCILIATION":
        req += ["Economics reconciliation status = OK"]
    return req


def baseline(ctx: dict) -> dict:
    ex = ctx.get("executive_state") or {}
    keys = [
        "snapshot_date", "latest_complete_period", "stock_units",
        "last_complete_sales_units", "ventas_promedio_3m",
        "ventas_promedio_6m", "absorcion_promedio_3m",
        "absorcion_promedio_6m", "months_to_zero",
        "gap_value", "commercial_placed_value", "target_value",
        "cumplimiento_actual", "economics_conciliacion"
    ]
    return {k: ex.get(k) for k in keys}


def evidence_gaps(ctx: dict) -> list[str]:
    ex = ctx.get("executive_state") or {}
    gaps = []
    raw = ex.get("evidence_gaps")
    if raw:
        gaps.append(str(raw))

    if not (ctx.get("layer_readiness") or {}).get("predictive"):
        gaps.append("sin evidencia prospectiva por proyecto")
    if not (ctx.get("layer_readiness") or {}).get("decision"):
        gaps.append("sin decisión gobernada por proyecto")
    if not (ctx.get("layer_readiness") or {}).get("outcome"):
        gaps.append("sin outcome registrado por proyecto")
    if str(ex.get("economics_conciliacion") or "") not in ("", "OK"):
        gaps.append("conciliación económica pendiente")

    return list(dict.fromkeys(gaps))


def build_analysis(row: dict) -> dict:
    ctx = row["context_json"]
    ex = ctx.get("executive_state") or {}
    archetype = derive_archetype(ctx)
    score = priority_score(ctx, archetype)
    pstate = predictive_state(ctx)
    estate = exec_status(ctx)
    esignal = economic_signal(ctx)
    primary, secondary = metric_candidates(ctx, archetype)

    analysis = {
        "meta": {
            "version": VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_key": row["project_key"],
            "project_name": row["project_name"],
            "context_snapshot_id": row["context_snapshot_id"],
        },
        "classification": {
            "archetype": archetype,
            "priority_score": score,
            "evidence_level": effective_evidence_level(ctx, row.get("highest_claim_level")),
            "economic_signal": esignal,
            "predictive_state": pstate,
            "execution_state": estate,
        },
        "observed": {
            "stock_units": ex.get("stock_units"),
            "months_to_zero": ex.get("months_to_zero"),
            "gap_value": ex.get("gap_value"),
            "sales_units": ex.get("sales_units"),
            "cumplimiento_actual": ex.get("cumplimiento_actual"),
            "economics_conciliacion": ex.get("economics_conciliacion"),
        },
        "portfolio_position": ctx.get("portfolio_comparison") or {},
        "hypothesis": hypothesis_for(ctx, archetype),
        "proposed_action": proposed_action(ctx, archetype),
        "primary_metric": primary,
        "secondary_metrics": secondary,
        "baseline": baseline(ctx),
        "evidence_gaps": evidence_gaps(ctx),
        "required_before_execution": required_before_execution(ctx, archetype),
        "questions": [
            h.get("question")
            for h in (ctx.get("ai_hypotheses") or [])
            if h.get("question")
        ][:5],
    }
    return analysis


def contract_from_analysis(row: dict, analysis: dict) -> dict:
    ctx = row["context_json"]
    ex = ctx.get("executive_state") or {}
    c = analysis["classification"]

    return {
        "project_key": row["project_key"],
        "project_name": row["project_name"],
        "context_snapshot_id": row["context_snapshot_id"],
        "archetype": c["archetype"],
        "priority_score": c["priority_score"],
        "contract_type": contract_type(c["archetype"]),
        "hypothesis": analysis["hypothesis"],
        "proposed_action": analysis["proposed_action"],
        "owner_suggested": ex.get("suggested_owner"),
        "deadline": None,
        "primary_metric": analysis["primary_metric"],
        "secondary_metrics": analysis["secondary_metrics"],
        "baseline": analysis["baseline"],
        "success_criterion": "TO_DEFINE_EX_ANTE",
        "value_at_risk": ex.get("gap_value"),
        "value_to_capture": ex.get("value_to_capture"),
        "action_cost": ex.get("action_cost"),
        "expected_roi": ex.get("expected_roi"),
        "evidence_level": c["evidence_level"],
        "evidence_gaps": analysis["evidence_gaps"],
        "required_before_execution": analysis["required_before_execution"],
        "status": "DRAFT_REVIEW_REQUIRED",
    }


def persist(cur, row: dict, analysis: dict, contract: dict):
    ah = stable_hash(analysis)
    cur.execute(
        """
        INSERT INTO analytics.project_ai_analysis_snapshot_v291(
            analysis_hash, project_key, project_name, context_snapshot_id,
            archetype, priority_score, evidence_level, economic_signal,
            predictive_state, execution_state, analysis_json
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT(project_key, analysis_hash) DO NOTHING
        """,
        (
            ah, row["project_key"], row["project_name"], row["context_snapshot_id"],
            analysis["classification"]["archetype"],
            analysis["classification"]["priority_score"],
            row.get("highest_claim_level"),
            analysis["classification"]["economic_signal"],
            analysis["classification"]["predictive_state"],
            analysis["classification"]["execution_state"],
            json.dumps(analysis, ensure_ascii=False, default=jd),
        ),
    )

    ch = stable_hash(contract)
    cur.execute(
        """
        INSERT INTO decision_intelligence.project_decision_contract_draft_v291(
            draft_hash, project_key, project_name, context_snapshot_id,
            archetype, priority_score, contract_type,
            hypothesis, proposed_action, owner_suggested,
            deadline, primary_metric, secondary_metrics, baseline_json,
            success_criterion, value_at_risk, value_to_capture,
            action_cost, expected_roi, evidence_level,
            evidence_gaps, required_before_execution, status
        )
        VALUES(
            %s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s::jsonb,%s::jsonb,
            %s,%s,%s,%s,%s,%s,
            %s::jsonb,%s::jsonb,%s
        )
        ON CONFLICT(project_key, draft_hash) DO NOTHING
        """,
        (
            ch, contract["project_key"], contract["project_name"],
            contract["context_snapshot_id"], contract["archetype"],
            contract["priority_score"], contract["contract_type"],
            contract["hypothesis"], contract["proposed_action"],
            contract["owner_suggested"], contract["deadline"],
            contract["primary_metric"],
            json.dumps(contract["secondary_metrics"], ensure_ascii=False),
            json.dumps(contract["baseline"], ensure_ascii=False, default=jd),
            contract["success_criterion"], contract["value_at_risk"],
            contract["value_to_capture"], contract["action_cost"],
            contract["expected_roi"], contract["evidence_level"],
            json.dumps(contract["evidence_gaps"], ensure_ascii=False),
            json.dumps(contract["required_before_execution"], ensure_ascii=False),
            contract["status"],
        ),
    )


def evidence_label(text: str, label: str) -> str:
    return f"[{label}] {text}"


def render_project_md(analysis: dict, contract: dict) -> str:
    m = analysis["meta"]
    c = analysis["classification"]
    o = analysis["observed"]

    lines = [
        f"# {m['project_name']} ({m['project_key']}) — AI Project Analyst v2.9.1",
        "",
        "## Executive situation",
        "",
        evidence_label(
            f"Arquetipo operativo: {c['archetype']}; prioridad {c['priority_score']}/100.",
            "DERIVED"
        ),
        "",
        evidence_label(
            f"Stock={o.get('stock_units')}; meses de cobertura={o.get('months_to_zero')}; "
            f"gap económico={o.get('gap_value')}; cumplimiento={o.get('cumplimiento_actual')}.",
            "OBSERVED"
        ),
        "",
        evidence_label(
            f"Estado predictivo={c['predictive_state']}; estado de ejecución={c['execution_state']}; "
            f"nivel máximo de evidencia={c['evidence_level']}.",
            "DERIVED"
        ),
        "",
        "## Decision hypothesis",
        "",
        evidence_label(analysis["hypothesis"], "RECOMMENDED"),
        "",
        "## Proposed next move",
        "",
        evidence_label(analysis["proposed_action"], "RECOMMENDED"),
        "",
        "## Evidence questions",
        "",
    ]
    for q in analysis["questions"]:
        lines.append(f"- {evidence_label(q, 'RECOMMENDED')}")

    lines += [
        "",
        "## Draft decision contract — HUMAN REVIEW REQUIRED",
        "",
        f"- Contract type: `{contract['contract_type']}`",
        f"- Owner suggested: `{contract['owner_suggested']}`",
        f"- Deadline: `{contract['deadline']}`",
        f"- Primary metric: `{contract['primary_metric']}`",
        f"- Success criterion: `{contract['success_criterion']}`",
        f"- Status: `{contract['status']}`",
        "",
        "### Frozen baseline",
        "",
        "```json",
        json.dumps(contract["baseline"], ensure_ascii=False, indent=2, default=jd),
        "```",
        "",
        "### Must exist before execution",
        "",
    ]
    for x in contract["required_before_execution"]:
        lines.append(f"- {x}")

    lines += [
        "",
        "### Evidence gaps",
        "",
    ]
    for x in contract["evidence_gaps"] or ["No explicit gap captured."]:
        lines.append(f"- {x}")

    lines += [
        "",
        "> This is an AI-assisted draft. It is not an approved action and does not establish causality.",
    ]
    return "\n".join(lines) + "\n"


def render_portfolio_md(items: list[tuple[dict, dict]]) -> str:
    ordered = sorted(items, key=lambda x: x[0]["classification"]["priority_score"], reverse=True)

    lines = [
        "# Medallio Active Portfolio — AI Command Center v2.9.1",
        "",
        "This ranking prioritizes what deserves analysis/execution attention; it is not an automatic capital allocation.",
        "",
        "| Rank | Project | Score | Archetype | Evidence | Predictive | Execution | Contract |",
        "|---:|---|---:|---|---|---|---|---|",
    ]
    for i, (a, c) in enumerate(ordered, 1):
        cl = a["classification"]
        lines.append(
            f"| {i} | {a['meta']['project_name']} ({a['meta']['project_key']}) | "
            f"{cl['priority_score']} | {cl['archetype']} | {cl['evidence_level']} | "
            f"{cl['predictive_state']} | {cl['execution_state']} | {c['contract_type']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "- `EXECUTION_CONTRACT`: stop generating more recommendations; convert the existing recommendation into an owned, dated, measurable action.",
        "- `DATA_RECONCILIATION`: do not use economic value for an irreversible decision until reconciliation is resolved.",
        "- `VALUE_CAPTURE_DESIGN`: quantify the economic opportunity before choosing a commercial/pricing intervention.",
        "- `DIAGNOSTIC_TO_PREDICTIVE`: close prospective forecast coverage while keeping decisions diagnostic.",
        "- `CLOSEOUT_*`: optimize closure, margin and learning rather than maximizing volume.",
        "",
        "## Governance",
        "",
        "No draft is executable until deadline, primary metric, baseline, success criterion and required evidence have been reviewed by a human owner.",
    ]
    return "\n".join(lines) + "\n"


def run(root: Path, conn, project: str | None = None):
    keys = active_keys(root)
    if project:
        keys = [project]

    with conn.cursor() as cur:
        rows = fetch_dicts(
            cur,
            """
            SELECT
                context_snapshot_id,
                project_key,
                project_name,
                highest_claim_level,
                context_json
            FROM analytics.v_project_context_latest_v290
            WHERE project_key = ANY(%s)
            """,
            (keys,)
        )

        by_key = {r["project_key"]: r for r in rows}
        items = []

        base = root / "artifacts" / "project_ai_analyst_v291"
        base.mkdir(parents=True, exist_ok=True)

        for key in keys:
            row = by_key.get(key)
            if not row:
                print(f"[V2.9.1] {key}: context missing")
                continue

            if isinstance(row["context_json"], str):
                row["context_json"] = json.loads(row["context_json"])

            analysis = build_analysis(row)
            contract = contract_from_analysis(row, analysis)
            persist(cur, row, analysis, contract)

            folder = base / key
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "analysis.json").write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2, default=jd),
                encoding="utf-8"
            )
            (folder / "decision_contract_draft.json").write_text(
                json.dumps(contract, ensure_ascii=False, indent=2, default=jd),
                encoding="utf-8"
            )
            (folder / "ai_project_brief.md").write_text(
                render_project_md(analysis, contract), encoding="utf-8"
            )

            items.append((analysis, contract))
            cl = analysis["classification"]
            print(
                f"[V2.9.1] {key} | score={cl['priority_score']} | "
                f"archetype={cl['archetype']} | evidence={cl['evidence_level']} | "
                f"predictive={cl['predictive_state']} | execution={cl['execution_state']}"
            )

        conn.commit()

    if items:
        (base / "active_portfolio_command_center.md").write_text(
            render_portfolio_md(items), encoding="utf-8"
        )

        rows_csv = []
        for analysis, contract in items:
            cl = analysis["classification"]
            rows_csv.append({
                "project_key": analysis["meta"]["project_key"],
                "project_name": analysis["meta"]["project_name"],
                "priority_score": cl["priority_score"],
                "archetype": cl["archetype"],
                "evidence_level": cl["evidence_level"],
                "economic_signal": cl["economic_signal"],
                "predictive_state": cl["predictive_state"],
                "execution_state": cl["execution_state"],
                "contract_type": contract["contract_type"],
                "owner_suggested": contract["owner_suggested"],
                "deadline": contract["deadline"],
                "primary_metric": contract["primary_metric"],
                "status": contract["status"],
            })
        rows_csv.sort(key=lambda r: r["priority_score"], reverse=True)

        with (base / "active_portfolio_priority.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as f:
            w = csv.DictWriter(f, fieldnames=list(rows_csv[0].keys()))
            w.writeheader()
            w.writerows(rows_csv)

    return items


def status(conn):
    with conn.cursor() as cur:
        if not relation_exists(cur, "analytics.v_active_portfolio_priority_v291"):
            print("[V2.9.1] schema not installed")
            return
        rows = fetch_dicts(
            cur,
            """
            SELECT *
            FROM analytics.v_active_portfolio_priority_v291
            ORDER BY priority_score DESC NULLS LAST, project_key
            """
        )
    print(f"[V2.9.1] active rows={len(rows)}")
    for r in rows:
        print(
            f"  {r['project_key']} | {r['priority_score']} | "
            f"{r['archetype']} | contract={r.get('contract_type')} | "
            f"status={r.get('contract_status')}"
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", nargs="?", choices=["install", "refresh", "all", "status"], default="status")
    p.add_argument("--project", default=None)
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)

    with connect_postgres(settings) as conn:
        if args.command in ("install", "all"):
            install_schema(root, conn)
            print("[V2.9.1] schema: OK")

        if args.command in ("refresh", "all"):
            run(root, conn, args.project)

        if args.command == "status":
            status(conn)


if __name__ == "__main__":
    main()
