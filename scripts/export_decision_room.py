"""Exportar agregados reales de Medallio para importación local en la Sala de decisiones.

No publica datos en internet. No consulta Redshift ni exporta registros de clientes.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


HISTORY_SQL = """
SELECT p.codigo_proyecto, p.nombre_proyecto, p.periodo_mes, p.fecha_corte,
       p.stock_inicial, p.ventas_mes, p.stock_final, p.unidades_revision,
       a.separaciones_brutas
FROM analytics.comercial_proyecto_mes p
LEFT JOIN analytics.agg_ventas_mensual a
  ON a.codigo_proyecto = p.codigo_proyecto AND a.periodo_mes = p.periodo_mes
WHERE p.codigo_proyecto = ANY(%s)
  AND NOT p.mes_parcial
  AND p.periodo_mes >= %s
ORDER BY p.codigo_proyecto, p.periodo_mes
"""

FORECAST_SQL = """
SELECT project, run_id::text, origin, forecast_month, horizon, model,
       monthly_prediction, prediction, lower80, upper80,
       stock_remaining, evidence_level, created_at
FROM analytics.v_commercial_forecast_monthly
WHERE project = ANY(%s) AND horizon BETWEEN 1 AND 6
ORDER BY project, created_at DESC, run_id DESC, horizon
"""


def _day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError("Fecha inválida en el mart")


def _count(value: Any, field: str) -> int:
    if isinstance(value, bool) or value is None or int(value) != value or value < 0:
        raise ValueError(f"{field} debe ser un conteo no negativo")
    return int(value)


def build_packet(history_rows: list[dict], forecast_rows: list[dict], generated_at: str) -> dict:
    """Valida los hechos y conserva NULL donde Medallio aún no tiene contrato."""
    if not history_rows or len(history_rows) > 1200:
        raise ValueError("Se requieren 1–1200 filas mensuales")
    projects: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for raw in history_rows:
        code, name = raw["codigo_proyecto"], raw["nombre_proyecto"]
        if not isinstance(code, str) or not code or not isinstance(name, str) or not name:
            raise ValueError("Proyecto sin identidad legible")
        month, cutoff = _day(raw["periodo_mes"]), _day(raw["fecha_corte"])
        if month.day != 1 or cutoff < month:
            raise ValueError("Corte o mes inválido")
        key = (code, month.isoformat())
        if key in seen:
            raise ValueError("Mes duplicado para un proyecto")
        seen.add(key)
        stock_open = _count(raw["stock_inicial"], "stock_inicial")
        sales = _count(raw["ventas_mes"], "ventas_mes")
        stock_close = _count(raw["stock_final"], "stock_final")
        if stock_open - sales != stock_close:
            raise ValueError(f"Stock no concilia: {code} {month}")
        separations = raw["separaciones_brutas"]
        if separations is not None:
            separations = _count(separations, "separaciones_brutas")
        project = projects.setdefault(code, {
            "code": code, "name": name, "history": [], "forecast": [],
            "forecast_meta": None,
        })
        if project["name"] != name:
            raise ValueError("Nombre de proyecto inconsistente")
        project["history"].append({
            "month": month.isoformat(), "source_cutoff": cutoff.isoformat(),
            "stock_open": stock_open, "stock_close": stock_close,
            "minutas": sales, "separations": separations,
            "review_units": _count(raw["unidades_revision"], "unidades_revision"),
            "leads": None, "revenue_pen": None, "margin_pen": None,
        })
    if len(projects) > 5:
        raise ValueError("Máximo cinco proyectos por archivo")
    runs: dict[tuple[str, str], list[dict]] = {}
    for row in forecast_rows:
        code = row["project"]
        if code not in projects:
            continue
        if not 1 <= int(row["horizon"]) <= 6:
            continue
        runs.setdefault((code, str(row["run_id"])), []).append(row)
    latest_by_project: dict[str, list[dict]] = {}
    for (code, run_id), rows in runs.items():
        if code not in latest_by_project or (
            max(str(r["created_at"]) for r in rows), run_id
        ) > (
            max(str(r["created_at"]) for r in latest_by_project[code]),
            str(latest_by_project[code][0]["run_id"]),
        ):
            latest_by_project[code] = rows
    for code, rows in latest_by_project.items():
        for row in rows:
            monthly = float(row["monthly_prediction"])
            cumulative = float(row["prediction"])
            if not 0 <= monthly <= 100000 or not 0 <= cumulative <= 100000:
                raise ValueError("Pronóstico fuera de rango")
            projects[code]["forecast_meta"] = {
                "run_id": str(row["run_id"]), "origin": _day(row["origin"]).isoformat(),
                "model": str(row["model"]), "evidence_level": str(row["evidence_level"]),
                "issued_at": str(row["created_at"]),
            }
            lo = row["lower80"]
            hi = row["upper80"]
            projects[code]["forecast"].append({
                "month": _day(row["forecast_month"]).replace(day=1).isoformat(),
                "horizon": int(row["horizon"]),
                "minutas_monthly": monthly,
                "minutas_cumulative": cumulative,
                "cumulative_lower80": float(lo) if lo is not None else None,
                "cumulative_upper80": float(hi) if hi is not None else None,
                "stock_remaining": float(row["stock_remaining"]) if row["stock_remaining"] is not None else None,
            })
    for project in projects.values():
        project["history"].sort(key=lambda r: r["month"])
        project["forecast"].sort(key=lambda r: r["horizon"])
        if len({r["horizon"] for r in project["forecast"]}) != len(project["forecast"]):
            raise ValueError("Horizonte de pronóstico duplicado")
    return {
        "contract": "medallio_decision_room_v1", "origin": "MEDALLIO_LOCAL_AGGREGATE",
        "generated_at": generated_at,
        "definitions": {
            "minutas": "ventas_mes de analytics.comercial_proyecto_mes; venta documental gobernada",
            "separations": "separaciones_brutas de analytics.agg_ventas_mensual; otro universo, no tasa de cohorte",
            "stock": "stock reconstruido retrospectivamente; no snapshot histórico as-issued",
            "forecast": "v_commercial_forecast_monthly; 1–6 meses, pronóstico mensual derivado de horizontes acumulados",
            "missing": "leads, ingresos, margen y elasticidades no se fabrican",
        },
        "projects": list(projects.values()),
    }


def read_source(dsn: str, codes: list[str], from_month: date) -> tuple[list[dict], list[dict]]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '30s'")
            cur.execute(HISTORY_SQL, (codes, from_month))
            history = cur.fetchall()
            cur.execute("SELECT to_regclass('analytics.v_commercial_forecast_monthly')")
            forecast = []
            if cur.fetchone()["to_regclass"] is not None:
                cur.execute(FORECAST_SQL, (codes,))
                forecast = cur.fetchall()
    return history, forecast


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", required=True, help="Código de proyecto; repetir hasta cinco veces")
    parser.add_argument("--from-month", default="2025-01-01")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= len(set(args.project)) <= 5 or len(args.project) != len(set(args.project)):
        parser.error("Elija 1–5 códigos sin duplicados")
    if args.output.exists():
        parser.error("El archivo de salida ya existe")
    dsn = os.getenv("MEDALLIO_DSN")
    if not dsn:
        parser.error("Configure MEDALLIO_DSN para la base PostgreSQL local")
    history, forecast = read_source(dsn, args.project, date.fromisoformat(args.from_month))
    packet = build_packet(history, forecast, datetime.now(timezone.utc).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(packet, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Archivo generado: {args.output} | proyectos={len(packet['projects'])} | filas={sum(len(p['history']) for p in packet['projects'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
