from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg
import yaml
from dotenv import load_dotenv
from matplotlib.backends.backend_pdf import PdfPages


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQL_PATH = ROOT / "sql" / "60_pricing_study" / "00_pricing_study.sql"
DEFAULT_CONFIG_PATH = ROOT / "config" / "pricing_study.yml"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "pricing_study"

NAVY = "#0B2D5C"
BLUE = "#1D5FBF"
GREEN = "#5F9E45"
PURPLE = "#7253A5"
INK = "#1E293B"
MUTED = "#64748B"
LIGHT = "#F4F7FB"
BORDER = "#D8E0EA"
RED = "#B94A48"
AMBER = "#A96A00"


@dataclass(frozen=True)
class PricingStudyResult:
    pdf_path: Path
    png_path: Path
    project_scorecard_csv: Path
    scenario_csv: Path
    unit_actions_csv: Path
    evidence: dict[str, Any]


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def _connect() -> psycopg.Connection:
    _load_env()
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DATABASE", "medallio_dw"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"),
        connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")),
    )


def _read_df(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def _load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


def install_pricing_study_sql(sql_path: Path = DEFAULT_SQL_PATH) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def capture_price_snapshot(snapshot_date: str | None = None) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            if snapshot_date:
                cur.execute(
                    "CALL pricing_analytics.capture_price_snapshot(%s::date)",
                    (snapshot_date,),
                )
            else:
                cur.execute("CALL pricing_analytics.capture_price_snapshot()")
        conn.commit()


def _project_clause(project: str | None, alias: str = "") -> tuple[str, tuple[Any, ...]]:
    if not project:
        return "", ()
    prefix = f"{alias}." if alias else ""
    clause = (
        f"WHERE upper(coalesce({prefix}nombre_proyecto, '')) LIKE upper(%s) "
        f"   OR upper(coalesce({prefix}codigo_proyecto, '')) LIKE upper(%s)"
    )
    needle = f"%{project.strip()}%"
    return clause, (needle, needle)


def fetch_project_scorecard(project: str | None = None) -> pd.DataFrame:
    where, params = _project_clause(project)
    return _read_df(
        f"""
        SELECT *
        FROM pricing_analytics.v_pricing_project_scorecard
        {where}
        ORDER BY coalesce(nombre_proyecto, codigo_proyecto)
        """,
        params,
    )


def fetch_unit_positioning(project: str | None = None) -> pd.DataFrame:
    where, params = _project_clause(project)
    return _read_df(
        f"""
        SELECT *
        FROM pricing_analytics.v_pricing_unit_positioning
        {where}
        ORDER BY coalesce(nombre_proyecto, codigo_proyecto), codigo_unidad
        """,
        params,
    )


def fetch_evidence(project: str | None = None) -> dict[str, Any]:
    history_where, history_params = _project_clause(project, "h")
    events_where, events_params = _project_clause(project, "e")

    hist = _read_df(
        f"""
        SELECT
            count(DISTINCT h.snapshot_date) AS snapshot_days,
            min(h.snapshot_date) AS first_snapshot_date,
            max(h.snapshot_date) AS last_snapshot_date,
            count(*) AS snapshot_rows
        FROM pricing_analytics.fact_precio_unidad_diario h
        {history_where}
        """,
        history_params,
    )
    events = _read_df(
        f"""
        SELECT
            count(*) AS price_change_events,
            count(DISTINCT e.unidad_fuente_key) AS units_with_price_change,
            min(e.snapshot_date) AS first_change_date,
            max(e.snapshot_date) AS last_change_date
        FROM pricing_analytics.v_price_change_events e
        {events_where}
        """,
        events_params,
    )

    out: dict[str, Any] = {}
    if not hist.empty:
        out.update(hist.iloc[0].to_dict())
    if not events.empty:
        out.update(events.iloc[0].to_dict())
    return out


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_scenarios(scorecard: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    planning = config.get("planning", {})
    deltas = planning.get("scenario_price_deltas", [-0.05, -0.025, 0.0, 0.025, 0.05])
    elasticity = float(planning.get("stress_test_elasticity", -1.25))
    min_retention = float(planning.get("min_absorption_retention_ratio", 0.80))

    rows: list[dict[str, Any]] = []
    for _, r in scorecard.iterrows():
        project = r.get("nombre_proyecto") or r.get("codigo_proyecto") or "Proyecto"
        available = max(_num(r.get("departamentos_disponibles")), _num(r.get("stock_fin")))
        avg_price = _num(r.get("precio_lista_promedio_disponible"))
        baseline_abs = np.clip(_num(r.get("absorcion_neta_30d")), 0.0, 0.95)

        for delta in deltas:
            delta = float(delta)
            if baseline_abs > 0:
                adjusted_abs = baseline_abs * ((1.0 + delta) ** elasticity)
                adjusted_abs = float(np.clip(adjusted_abs, 0.0, 0.95))
                sell_through_90d = 1.0 - (1.0 - adjusted_abs) ** 3
            else:
                adjusted_abs = 0.0
                sell_through_90d = 0.0

            projected_units = min(available, available * sell_through_90d)
            scenario_price = avg_price * (1.0 + delta)
            projected_revenue = projected_units * scenario_price
            eligible = (
                delta == 0.0
                or baseline_abs <= 0
                or adjusted_abs >= baseline_abs * min_retention
            )
            rows.append(
                {
                    "codigo_proyecto": r.get("codigo_proyecto"),
                    "proyecto": project,
                    "price_delta_pct": delta,
                    "stress_test_elasticity": elasticity,
                    "baseline_absorption_30d": baseline_abs,
                    "scenario_absorption_30d": adjusted_abs,
                    "available_units_proxy": available,
                    "average_list_price": avg_price,
                    "scenario_average_price": scenario_price,
                    "projected_sell_through_90d": sell_through_90d,
                    "projected_units_90d": projected_units,
                    "projected_revenue_90d": projected_revenue,
                    "passes_absorption_guardrail": bool(eligible),
                    "scenario_mode": "STRESS_TEST_NOT_CAUSAL",
                }
            )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    result["recommended_in_stress_test"] = False
    for project, idx in result.groupby("proyecto").groups.items():
        candidate = result.loc[idx]
        eligible = candidate[candidate["passes_absorption_guardrail"]]
        if eligible.empty:
            chosen = candidate.iloc[(candidate["price_delta_pct"].abs()).argmin()].name
        else:
            chosen = eligible["projected_revenue_90d"].idxmax()
        result.loc[chosen, "recommended_in_stress_test"] = True
    return result


def classify_unit_actions(
    units: pd.DataFrame,
    scorecard: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    if units.empty:
        return units.copy()

    policy = config.get("unit_review_policy", {})
    high_idx = float(policy.get("high_price_index", 1.08))
    low_idx = float(policy.get("low_price_index", 0.92))
    slow_months = float(policy.get("slow_stock_months", 6.0))
    fast_months = float(policy.get("fast_stock_months", 3.0))
    review_down = float(policy.get("review_down_delta", -0.025))
    review_up = float(policy.get("review_up_delta", 0.025))

    project_cols = scorecard[
        ["codigo_proyecto", "meses_stock_ventas_30d", "absorcion_neta_30d"]
    ].copy()
    out = units.merge(project_cols, on="codigo_proyecto", how="left")
    out = out[out["estado_bucket"].eq("DISPONIBLE")].copy()

    idx = pd.to_numeric(out["indice_precio_vs_benchmark_interno"], errors="coerce")
    months = pd.to_numeric(out["meses_stock_ventas_30d"], errors="coerce")

    conditions = [
        idx.ge(high_idx) & months.ge(slow_months),
        idx.le(low_idx) & months.le(fast_months),
    ]
    out["accion_revision"] = np.select(
        conditions,
        ["REVISAR_DESCUENTO", "TEST_SUBIDA"],
        default="MANTENER",
    )
    out["delta_sugerido_revision"] = np.select(
        conditions,
        [review_down, review_up],
        default=0.0,
    ).astype(float)
    out["precio_lista_sugerido_revision"] = (
        pd.to_numeric(out["precio_lista"], errors="coerce")
        * (1.0 + out["delta_sugerido_revision"])
    )

    out["motivo_revision"] = np.select(
        conditions,
        [
            "Precio m2 sobre corredor interno y stock lento: revisar descuento/precio.",
            "Precio m2 bajo corredor interno y stock rápido: candidato a test de subida.",
        ],
        default="Dentro de corredor o sin evidencia suficiente para mover precio.",
    )
    out["prioridad_revision"] = (
        (idx.sub(1.0).abs().fillna(0.0) * 100.0)
        + months.fillna(0.0).clip(lower=0.0)
    )
    out["decision_status"] = "REQUIERE_APROBACION_COMERCIAL"
    return out.sort_values(["accion_revision", "prioridad_revision"], ascending=[True, False])


def _fmt_money(value: float) -> str:
    value = _num(value)
    if abs(value) >= 1_000_000:
        return f"S/ {value / 1_000_000:,.1f} MM"
    if abs(value) >= 1_000:
        return f"S/ {value / 1_000:,.0f} mil"
    return f"S/ {value:,.0f}"


def _fmt_pct(value: float) -> str:
    return f"{100 * _num(value):.1f}%"


def _add_card(fig: plt.Figure, x: float, y: float, w: float, h: float, title: str, value: str, note: str = "") -> None:
    ax = fig.add_axes([x, y, w, h])
    ax.set_facecolor("white")
    for s in ax.spines.values():
        s.set_edgecolor(BORDER)
        s.set_linewidth(1.0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.05, 0.78, title.upper(), fontsize=8, color=MUTED, weight="bold", transform=ax.transAxes)
    ax.text(0.05, 0.43, value, fontsize=17, color=NAVY, weight="bold", transform=ax.transAxes)
    if note:
        ax.text(0.05, 0.10, note, fontsize=7.5, color=MUTED, transform=ax.transAxes)


def _portfolio_kpis(scorecard: pd.DataFrame) -> dict[str, float]:
    available = pd.to_numeric(scorecard.get("departamentos_disponibles"), errors="coerce").fillna(0)
    stock_value = pd.to_numeric(scorecard.get("valor_lista_disponible"), errors="coerce").fillna(0)
    absorption = pd.to_numeric(scorecard.get("absorcion_neta_30d"), errors="coerce")
    months = pd.to_numeric(scorecard.get("meses_stock_ventas_30d"), errors="coerce")
    weights = available.where(available > 0, 1)
    weighted_abs = np.average(absorption.fillna(0), weights=weights) if len(scorecard) else 0
    weighted_months = np.average(months.fillna(0), weights=weights) if len(scorecard) else 0
    return {
        "projects": float(len(scorecard)),
        "available": float(available.sum()),
        "stock_value": float(stock_value.sum()),
        "absorption": float(weighted_abs),
        "months_stock": float(weighted_months),
    }


def _portfolio_scenario(scenarios: pd.DataFrame) -> pd.DataFrame:
    if scenarios.empty:
        return scenarios
    grouped = (
        scenarios.groupby("price_delta_pct", as_index=False)
        .agg(
            projected_revenue_90d=("projected_revenue_90d", "sum"),
            projected_units_90d=("projected_units_90d", "sum"),
            passes=("passes_absorption_guardrail", "all"),
        )
        .sort_values("price_delta_pct")
    )
    base = grouped.loc[grouped["price_delta_pct"].abs().idxmin(), "projected_revenue_90d"]
    grouped["revenue_index_vs_base"] = np.where(base > 0, grouped["projected_revenue_90d"] / base, np.nan)
    return grouped


def _insights(scorecard: pd.DataFrame, scenarios: pd.DataFrame) -> list[str]:
    insights: list[str] = []
    if not scorecard.empty:
        months = pd.to_numeric(scorecard["meses_stock_ventas_30d"], errors="coerce")
        if months.notna().any():
            i = months.idxmax()
            project = scorecard.loc[i, "nombre_proyecto"] or scorecard.loc[i, "codigo_proyecto"]
            insights.append(f"Mayor presión de inventario: {project} con {months.loc[i]:.1f} meses de stock.")

        gap = pd.to_numeric(scorecard["gap_precio_m2_disponible_vs_vendido"], errors="coerce")
        if gap.notna().any():
            i = gap.abs().idxmax()
            project = scorecard.loc[i, "nombre_proyecto"] or scorecard.loc[i, "codigo_proyecto"]
            insights.append(f"Mayor gap lista vs vendido: {project} ({100 * gap.loc[i]:+.1f}% en mediana de S/m²).")

    port = _portfolio_scenario(scenarios)
    if not port.empty and port["projected_revenue_90d"].notna().any():
        eligible = port[port["passes"]]
        chosen = (eligible if not eligible.empty else port).loc[
            (eligible if not eligible.empty else port)["projected_revenue_90d"].idxmax()
        ]
        insights.append(
            f"Stress test: {100 * chosen['price_delta_pct']:+.1f}% maximiza el proxy de ingresos a 90 días bajo el guardrail configurado."
        )
    return insights[:3]


def _render_executive_page(
    scorecard: pd.DataFrame,
    scenarios: pd.DataFrame,
    evidence: dict[str, Any],
    title_scope: str,
) -> plt.Figure:
    fig = plt.figure(figsize=(16, 9), facecolor=LIGHT)
    fig.text(0.04, 0.955, "CASO DE USO: PRICING INMOBILIARIO", fontsize=24, weight="bold", color=NAVY)
    fig.text(0.04, 0.922, "Analítica para balancear precio, absorción y valor económico del inventario", fontsize=12, color=MUTED)
    fig.text(0.94, 0.952, title_scope, fontsize=10, ha="right", color=MUTED)

    top = [
        ("CONTEXTO", "Stock + precios + ventas + absorción desde Medallio DW"),
        ("PROBLEMA", "Un mismo descuento puede destruir margen o frenar absorción"),
        ("OBJETIVO", "Maximizar valor esperado sin romper velocidad comercial"),
        ("ENFOQUE", "Benchmark interno + absorción + escenarios + gobernanza"),
    ]
    for i, (h, txt) in enumerate(top):
        ax = fig.add_axes([0.04 + i * 0.235, 0.83, 0.22, 0.07])
        ax.set_facecolor("white")
        for s in ax.spines.values():
            s.set_edgecolor(BORDER)
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(0.04, 0.70, h, fontsize=8, weight="bold", color=BLUE, transform=ax.transAxes)
        ax.text(0.04, 0.18, txt, fontsize=7.6, color=INK, wrap=True, transform=ax.transAxes)

    flow = ["1  ANALIZAR", "2  SEGMENTAR", "3  SIMULAR", "4  RECOMENDAR"]
    for i, label in enumerate(flow):
        ax = fig.add_axes([0.04 + i * 0.235, 0.77, 0.22, 0.045])
        ax.set_facecolor("white")
        for s in ax.spines.values():
            s.set_edgecolor(BORDER)
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(0.5, 0.5, label, ha="center", va="center", fontsize=8.5, weight="bold", color=NAVY)

    k = _portfolio_kpis(scorecard)
    _add_card(fig, 0.04, 0.64, 0.17, 0.105, "Proyectos", f"{int(k['projects'])}", "en alcance")
    _add_card(fig, 0.225, 0.64, 0.17, 0.105, "Stock disponible", f"{int(k['available']):,}", "departamentos")
    _add_card(fig, 0.41, 0.64, 0.17, 0.105, "Valor lista", _fmt_money(k["stock_value"]), "inventario disponible")
    _add_card(fig, 0.595, 0.64, 0.17, 0.105, "Absorción neta 30d", _fmt_pct(k["absorption"]), "promedio ponderado")
    _add_card(fig, 0.78, 0.64, 0.17, 0.105, "Meses de stock", f"{k['months_stock']:.1f}", "proxy por ventas 30d")

    ax1 = fig.add_axes([0.05, 0.34, 0.42, 0.26], facecolor="white")
    x = pd.to_numeric(scorecard["precio_m2_mediana_disponible"], errors="coerce")
    y = 100 * pd.to_numeric(scorecard["absorcion_neta_30d"], errors="coerce")
    s = 50 + 7 * pd.to_numeric(scorecard["departamentos_disponibles"], errors="coerce").fillna(0)
    ax1.scatter(x, y, s=s.clip(50, 500), alpha=0.78, edgecolor="white", linewidth=0.8, color=BLUE)
    for _, r in scorecard.iterrows():
        xv = _num(r.get("precio_m2_mediana_disponible"), np.nan)
        yv = 100 * _num(r.get("absorcion_neta_30d"), np.nan)
        if np.isfinite(xv) and np.isfinite(yv):
            label = str(r.get("nombre_proyecto") or r.get("codigo_proyecto") or "")
            ax1.annotate(label[:16], (xv, yv), xytext=(4, 4), textcoords="offset points", fontsize=7, color=INK)
    ax1.set_title("PRECIO M² vs. ABSORCIÓN 30D", loc="left", fontsize=10, weight="bold", color=NAVY)
    ax1.set_xlabel("Mediana precio lista S/m²", fontsize=8, color=MUTED)
    ax1.set_ylabel("Absorción neta 30d (%)", fontsize=8, color=MUTED)
    ax1.grid(alpha=0.15)
    ax1.tick_params(labelsize=7)

    ax2 = fig.add_axes([0.50, 0.34, 0.22, 0.26], facecolor="white")
    tmp = scorecard.copy()
    tmp["meses"] = pd.to_numeric(tmp["meses_stock_ventas_30d"], errors="coerce")
    tmp["label"] = tmp["nombre_proyecto"].fillna(tmp["codigo_proyecto"]).astype(str)
    tmp = tmp.dropna(subset=["meses"]).sort_values("meses").tail(8)
    ax2.barh(tmp["label"], tmp["meses"], color=PURPLE, alpha=0.82)
    ax2.set_title("MESES DE STOCK", loc="left", fontsize=10, weight="bold", color=NAVY)
    ax2.tick_params(labelsize=7)
    ax2.grid(axis="x", alpha=0.15)

    ax3 = fig.add_axes([0.75, 0.34, 0.20, 0.26], facecolor="white")
    port = _portfolio_scenario(scenarios)
    if not port.empty:
        ax3.plot(100 * port["price_delta_pct"], 100 * port["revenue_index_vs_base"], marker="o", color=GREEN, linewidth=2)
        ax3.axhline(100, color=MUTED, linewidth=1, alpha=0.5)
    ax3.set_title("STRESS TEST DE PRECIO", loc="left", fontsize=10, weight="bold", color=NAVY)
    ax3.set_xlabel("Variación precio (%)", fontsize=8, color=MUTED)
    ax3.set_ylabel("Índice ingreso 90d (base=100)", fontsize=8, color=MUTED)
    ax3.tick_params(labelsize=7)
    ax3.grid(alpha=0.15)

    ax4 = fig.add_axes([0.05, 0.12, 0.58, 0.18], facecolor="white")
    for s0 in ax4.spines.values():
        s0.set_edgecolor(BORDER)
    ax4.set_xticks([]); ax4.set_yticks([])
    ax4.text(0.025, 0.82, "INSIGHTS EJECUTIVOS", fontsize=10, weight="bold", color=NAVY, transform=ax4.transAxes)
    insights = _insights(scorecard, scenarios)
    if not insights:
        insights = ["Aún no hay evidencia suficiente para emitir insights cuantitativos."]
    for i, txt in enumerate(insights):
        ax4.text(0.035, 0.60 - i * 0.22, f"✓  {txt}", fontsize=8.6, color=INK, transform=ax4.transAxes)

    ax5 = fig.add_axes([0.66, 0.12, 0.29, 0.18], facecolor="white")
    for s0 in ax5.spines.values():
        s0.set_edgecolor(BORDER)
    ax5.set_xticks([]); ax5.set_yticks([])
    days = int(_num(evidence.get("snapshot_days")))
    changes = int(_num(evidence.get("price_change_events")))
    ax5.text(0.04, 0.82, "EVIDENCIA DEL MODELO", fontsize=10, weight="bold", color=NAVY, transform=ax5.transAxes)
    ax5.text(0.04, 0.58, f"Snapshots de precio: {days} días", fontsize=8.5, color=INK, transform=ax5.transAxes)
    ax5.text(0.04, 0.39, f"Eventos de cambio: {changes}", fontsize=8.5, color=INK, transform=ax5.transAxes)
    ax5.text(0.04, 0.16, "Escenarios actuales = stress test. No son elasticidad causal.", fontsize=7.8, color=AMBER, weight="bold", transform=ax5.transAxes)

    fig.text(
        0.5,
        0.045,
        "NO SE TRATA DE SUBIR O BAJAR PRECIOS. SE TRATA DE COBRAR LO NECESARIO PARA MAXIMIZAR VALOR SIN ROMPER LA ABSORCIÓN.",
        ha="center",
        fontsize=11,
        weight="bold",
        color=NAVY,
    )
    return fig


def _render_unit_page(actions: pd.DataFrame, title_scope: str) -> plt.Figure:
    fig = plt.figure(figsize=(16, 9), facecolor=LIGHT)
    fig.text(0.04, 0.95, "MAPA DE UNIDADES A REVISAR", fontsize=22, weight="bold", color=NAVY)
    fig.text(0.94, 0.952, title_scope, fontsize=10, ha="right", color=MUTED)
    fig.text(0.04, 0.915, "Priorización heurística: corredor interno de S/m² + velocidad de stock del proyecto", fontsize=11, color=MUTED)

    ax1 = fig.add_axes([0.05, 0.48, 0.48, 0.36], facecolor="white")
    if not actions.empty:
        plot = actions.copy()
        x = pd.to_numeric(plot["area_total"], errors="coerce")
        y = pd.to_numeric(plot["indice_precio_vs_benchmark_interno"], errors="coerce")
        mapping = {"REVISAR_DESCUENTO": RED, "TEST_SUBIDA": GREEN, "MANTENER": BLUE}
        for action, g in plot.groupby("accion_revision"):
            ax1.scatter(
                pd.to_numeric(g["area_total"], errors="coerce"),
                pd.to_numeric(g["indice_precio_vs_benchmark_interno"], errors="coerce"),
                s=45,
                alpha=0.72,
                label=action,
                color=mapping.get(action, BLUE),
            )
        ax1.axhline(1.0, color=MUTED, linewidth=1)
        ax1.axhspan(0.95, 1.05, color="#DDE7F5", alpha=0.45)
        ax1.legend(fontsize=7, loc="best")
    ax1.set_title("ÍNDICE DE PRECIO INTERNO POR UNIDAD", loc="left", fontsize=10, weight="bold", color=NAVY)
    ax1.set_xlabel("Área total (m²)", fontsize=8, color=MUTED)
    ax1.set_ylabel("Precio m² / benchmark tipología", fontsize=8, color=MUTED)
    ax1.grid(alpha=0.15)
    ax1.tick_params(labelsize=7)

    ax2 = fig.add_axes([0.57, 0.48, 0.38, 0.36], facecolor="white")
    counts = actions["accion_revision"].value_counts() if not actions.empty else pd.Series(dtype=int)
    if not counts.empty:
        colors = [RED if i == "REVISAR_DESCUENTO" else GREEN if i == "TEST_SUBIDA" else BLUE for i in counts.index]
        ax2.barh(counts.index, counts.values, color=colors, alpha=0.82)
        for i, v in enumerate(counts.values):
            ax2.text(v + max(counts.values) * 0.02, i, str(v), va="center", fontsize=8, color=INK)
    ax2.set_title("DISTRIBUCIÓN DE ACCIONES DE REVISIÓN", loc="left", fontsize=10, weight="bold", color=NAVY)
    ax2.tick_params(labelsize=8)
    ax2.grid(axis="x", alpha=0.15)

    ax3 = fig.add_axes([0.05, 0.08, 0.90, 0.33], facecolor="white")
    ax3.axis("off")
    cols = [
        "nombre_proyecto",
        "codigo_unidad",
        "segmento_pricing",
        "precio_lista",
        "precio_m2_lista",
        "indice_precio_vs_benchmark_interno",
        "meses_stock_ventas_30d",
        "accion_revision",
    ]
    top = actions.sort_values("prioridad_revision", ascending=False).head(14).copy() if not actions.empty else pd.DataFrame(columns=cols)
    display_rows = []
    for _, r in top.iterrows():
        display_rows.append([
            str(r.get("nombre_proyecto") or r.get("codigo_proyecto") or "")[:14],
            str(r.get("codigo_unidad") or "")[:10],
            str(r.get("segmento_pricing") or "")[:12],
            _fmt_money(r.get("precio_lista")),
            f"{_num(r.get('precio_m2_lista')):,.0f}",
            f"{_num(r.get('indice_precio_vs_benchmark_interno')):.2f}x",
            f"{_num(r.get('meses_stock_ventas_30d')):.1f}",
            str(r.get("accion_revision") or ""),
        ])
    table = ax3.table(
        cellText=display_rows,
        colLabels=["Proyecto", "Unidad", "Tipología", "Precio", "S/m²", "Índice", "Meses", "Acción"],
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    table.scale(1, 1.35)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(BORDER)
        if row == 0:
            cell.set_facecolor(NAVY)
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("white")
    fig.text(0.05, 0.405, "TOP UNIDADES PARA REVISIÓN COMERCIAL", fontsize=10, weight="bold", color=NAVY)
    fig.text(0.05, 0.035, "Estas acciones son candidatos de revisión, no cambios automáticos. Requieren aprobación comercial y registro de outcome.", fontsize=8.5, color=AMBER)
    return fig


def _render_methodology_page(config: dict[str, Any], evidence: dict[str, Any], title_scope: str) -> plt.Figure:
    fig = plt.figure(figsize=(16, 9), facecolor=LIGHT)
    fig.text(0.04, 0.95, "CÓMO SE CONSTRUYE LA DECISIÓN DE PRICING", fontsize=22, weight="bold", color=NAVY)
    fig.text(0.94, 0.952, title_scope, fontsize=10, ha="right", color=MUTED)

    blocks = [
        ("1. DATO", "core.v_unidades_fuentes\n+ fact_absorcion_proyecto_diario\n+ snapshots diarios de precio"),
        ("2. EVIDENCIA", "Precio S/m², corredor interno,\nstock, absorción 30d, meses de stock,\ngap disponible vs vendido"),
        ("3. ESCENARIO", "Stress tests de variación de precio.\nElasticidad configurada = supuesto,\nno causalidad demostrada."),
        ("4. DECISIÓN", "Revisar descuento / mantener /\ntest de subida. Siempre con\naprobación y guardrails."),
        ("5. OUTCOME", "Registrar precio aplicado, fecha,\nseparaciones, ventas, margen y\nreversión posterior."),
    ]
    for i, (head, body) in enumerate(blocks):
        ax = fig.add_axes([0.04 + i * 0.19, 0.68, 0.175, 0.18])
        ax.set_facecolor("white")
        for s in ax.spines.values():
            s.set_edgecolor(BORDER)
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(0.05, 0.82, head, fontsize=9.5, weight="bold", color=BLUE, transform=ax.transAxes)
        ax.text(0.05, 0.58, body, fontsize=8.2, color=INK, va="top", transform=ax.transAxes)

    ax1 = fig.add_axes([0.05, 0.36, 0.42, 0.24], facecolor="white")
    ax1.set_xticks([]); ax1.set_yticks([])
    for s in ax1.spines.values(): s.set_edgecolor(BORDER)
    ax1.text(0.04, 0.84, "GATES DE EVIDENCIA", fontsize=11, weight="bold", color=NAVY, transform=ax1.transAxes)
    model_cfg = config.get("model_readiness", {})
    min_days = int(model_cfg.get("min_snapshot_days", 60))
    min_changes = int(model_cfg.get("min_price_change_events", 20))
    days = int(_num(evidence.get("snapshot_days")))
    changes = int(_num(evidence.get("price_change_events")))
    ready = days >= min_days and changes >= min_changes
    lines = [
        f"Snapshots: {days}/{min_days} días mínimos",
        f"Eventos de cambio: {changes}/{min_changes} mínimos",
        "Variación de precio ≠ causalidad: el gate solo habilita modelado, no lo valida.",
        f"Estado: {'LISTO PARA REVISIÓN DE MODELO' if ready else 'ACUMULANDO EVIDENCIA'}",
    ]
    for i, txt in enumerate(lines):
        ax1.text(0.05, 0.62 - i * 0.17, txt, fontsize=8.8, color=GREEN if i == 3 and ready else INK, transform=ax1.transAxes)

    ax2 = fig.add_axes([0.52, 0.36, 0.43, 0.24], facecolor="white")
    ax2.set_xticks([]); ax2.set_yticks([])
    for s in ax2.spines.values(): s.set_edgecolor(BORDER)
    ax2.text(0.04, 0.84, "GUARDRAILS PERMANENTES", fontsize=11, weight="bold", color=NAVY, transform=ax2.transAxes)
    guards = [
        "• No confundir benchmark interno con precio de mercado externo.",
        "• No publicar elasticidad causal sin identificación y validación temporal.",
        "• Toda recomendación debe conservar precio actual, supuesto, escenario y razón.",
        "• Todo cambio real debe registrar acción, aprobación y outcome observado.",
        "• Power BI / PDF consumen marts; no reconstruyen reglas de negocio.",
    ]
    for i, txt in enumerate(guards):
        ax2.text(0.05, 0.62 - i * 0.13, txt, fontsize=8.6, color=INK, transform=ax2.transAxes)

    ax3 = fig.add_axes([0.05, 0.08, 0.90, 0.20], facecolor=NAVY)
    ax3.set_xticks([]); ax3.set_yticks([])
    for s in ax3.spines.values(): s.set_visible(False)
    ax3.text(0.04, 0.70, "NORTH STAR", fontsize=10, weight="bold", color="white", transform=ax3.transAxes)
    ax3.text(0.04, 0.42, "Valor económico realizado por decisiones de pricing, sujeto a absorción, coherencia comercial y evidencia.", fontsize=15, weight="bold", color="white", transform=ax3.transAxes)
    ax3.text(0.04, 0.16, "El modelo no es el producto. El producto es el ciclo evidencia → decisión → acción → outcome → aprendizaje.", fontsize=9.5, color="#D9E5F5", transform=ax3.transAxes)
    return fig


def generate_pricing_study(
    project: str | None = None,
    *,
    install_sql: bool = False,
    capture_snapshot: bool = False,
    snapshot_date: str | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> PricingStudyResult:
    if install_sql:
        install_pricing_study_sql()
    if capture_snapshot:
        capture_price_snapshot(snapshot_date)

    config = _load_config(config_path)
    scorecard = fetch_project_scorecard(project)
    if scorecard.empty:
        scope = project or "portafolio"
        raise RuntimeError(f"No se encontraron datos de pricing para: {scope}")

    units = fetch_unit_positioning(project)
    evidence = fetch_evidence(project)
    scenarios = build_scenarios(scorecard, config)
    actions = classify_unit_actions(units, scorecard, config)

    generated_at = datetime.now()
    scope_slug = (project or "portafolio").strip().replace(" ", "_").replace("/", "-")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"Pricing_Inmobiliario_{scope_slug}_{generated_at:%Y_%m_%d}"
    pdf_path = output_dir / f"{stem}.pdf"
    png_path = output_dir / f"{stem}_executive.png"
    project_csv = output_dir / f"{stem}_scorecard.csv"
    scenario_csv = output_dir / f"{stem}_scenarios.csv"
    actions_csv = output_dir / f"{stem}_unit_actions.csv"

    scorecard.to_csv(project_csv, index=False, encoding="utf-8-sig")
    scenarios.to_csv(scenario_csv, index=False, encoding="utf-8-sig")
    actions.to_csv(actions_csv, index=False, encoding="utf-8-sig")

    title_scope = project or "Portafolio Medallio"
    page1 = _render_executive_page(scorecard, scenarios, evidence, title_scope)
    page1.savefig(png_path, dpi=180, bbox_inches="tight", facecolor=page1.get_facecolor())
    page2 = _render_unit_page(actions, title_scope)
    page3 = _render_methodology_page(config, evidence, title_scope)

    with PdfPages(pdf_path) as pdf:
        pdf.savefig(page1, bbox_inches="tight", facecolor=page1.get_facecolor())
        pdf.savefig(page2, bbox_inches="tight", facecolor=page2.get_facecolor())
        pdf.savefig(page3, bbox_inches="tight", facecolor=page3.get_facecolor())

    plt.close(page1)
    plt.close(page2)
    plt.close(page3)

    return PricingStudyResult(
        pdf_path=pdf_path,
        png_path=png_path,
        project_scorecard_csv=project_csv,
        scenario_csv=scenario_csv,
        unit_actions_csv=actions_csv,
        evidence=evidence,
    )
