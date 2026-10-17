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
from zoneinfo import ZoneInfo


LIMA = ZoneInfo("America/Lima")
EXPECTED_FORECAST_HORIZONS = tuple(range(1, 7))
STOCK_TOLERANCE = 1e-6
RATE_TOLERANCE = 1e-9

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

FUNNEL_SQL = """
SELECT codigo_proyecto, periodo_mes,
       leads, clientes_unicos,
       leads_identidad_mapeada, leads_identidad_ambigua, leads_identidad_sin_match,
       identity_match_rate, proformas, separaciones, minutas,
       commercial_cutoff, funnel_semantics
FROM analytics.v_decision_room_funnel_monthly
WHERE codigo_proyecto = ANY(%s)
  AND periodo_mes >= %s
ORDER BY codigo_proyecto, periodo_mes
"""


def _day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError("Fecha inválida en el mart")


def _generated_local_day(value: str) -> date:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LIMA).date()


def _count(value: Any, field: str) -> int:
    if isinstance(value, bool) or value is None or int(value) != value or value < 0:
        raise ValueError(f"{field} debe ser un conteo no negativo")
    return int(value)


def _optional_count(value: Any, field: str) -> int | None:
    return None if value is None else _count(value, field)


def _project_readiness(project: dict, generated_at: str) -> dict:
    """Evalúa cuatro gates fail-closed sin ocultar el proyecto del paquete."""
    history = project["history"]
    forecast = project["forecast"]
    forecast_meta = project["forecast_meta"]
    expected_cutoff = _generated_local_day(generated_at)

    latest_cutoff = max(_day(row["source_cutoff"]) for row in history)
    freshness_ok = latest_cutoff == expected_cutoff
    freshness = {
        "status": "PASS" if freshness_ok else "FAIL",
        "source_cutoff": latest_cutoff.isoformat(),
        "expected_cutoff": expected_cutoff.isoformat(),
        "age_days": (expected_cutoff - latest_cutoff).days,
    }

    horizons = sorted(row["horizon"] for row in forecast)
    missing_horizons = sorted(set(EXPECTED_FORECAST_HORIZONS) - set(horizons))
    extra_horizons = sorted(set(horizons) - set(EXPECTED_FORECAST_HORIZONS))
    forecast_ok = (
        forecast_meta is not None
        and horizons == list(EXPECTED_FORECAST_HORIZONS)
        and not missing_horizons
        and not extra_horizons
    )
    forecast_availability = {
        "status": "PASS" if forecast_ok else "FAIL",
        "horizons": horizons,
        "expected_horizons": list(EXPECTED_FORECAST_HORIZONS),
        "missing_horizons": missing_horizons,
        "extra_horizons": extra_horizons,
    }

    origin = forecast_meta["origin"] if forecast_meta else None
    origin_history = next((row for row in history if row["month"] == origin), None)
    implied_stocks = [
        row["stock_remaining"] + row["minutas_cumulative"]
        for row in forecast
        if row["stock_remaining"] is not None
    ]
    implied_consistent = (
        bool(forecast)
        and len(implied_stocks) == len(forecast)
        and max(implied_stocks) - min(implied_stocks) <= STOCK_TOLERANCE
    )
    forecast_origin_stock = implied_stocks[0] if implied_consistent else None
    history_origin_stock = origin_history["stock_close"] if origin_history else None
    stock_delta = (
        forecast_origin_stock - history_origin_stock
        if forecast_origin_stock is not None and history_origin_stock is not None
        else None
    )
    stock_ok = (
        implied_consistent
        and origin_history is not None
        and stock_delta is not None
        and abs(stock_delta) <= STOCK_TOLERANCE
    )
    stock_reconciliation = {
        "status": "PASS" if stock_ok else "FAIL",
        "origin": origin,
        "history_origin_stock": history_origin_stock,
        "forecast_origin_stock": forecast_origin_stock,
        "delta_units": 0.0 if stock_ok else stock_delta,
        "forecast_implied_stock_consistent": implied_consistent,
    }

    review_units_max = max(row["review_units"] for row in history)
    origin_review_units = origin_history["review_units"] if origin_history else None
    quality_ok = review_units_max == 0
    quality = {
        "status": "PASS" if quality_ok else "FAIL",
        "review_units_max": review_units_max,
        "origin_review_units": origin_review_units,
    }

    gates = {
        "freshness": freshness,
        "stock_reconciliation": stock_reconciliation,
        "quality": quality,
        "forecast_availability": forecast_availability,
    }
    reason_codes = {
        "freshness": "STALE_SOURCE",
        "stock_reconciliation": "STOCK_MISMATCH",
        "quality": "DATA_QUALITY_QUARANTINE",
        "forecast_availability": "FORECAST_INCOMPLETE",
    }
    failures = [name for name, gate in gates.items() if gate["status"] != "PASS"]
    return {
        "status": "READY" if not failures else "BLOCKED",
        "failures": failures,
        "blocking_reasons": [reason_codes[name] for name in failures],
        "gates": gates,
    }


def _attach_funnel(projects: dict[str, dict], funnel_rows: list[dict]) -> None:
    """Adjunta actividad mensual y reconcilia etapas ya gobernadas en history."""
    seen: set[tuple[str, str]] = set()
    for raw in funnel_rows:
        code = raw["codigo_proyecto"]
        if code not in projects:
            continue
        month = _day(raw["periodo_mes"])
        if month.day != 1:
            raise ValueError("Mes de funnel inválido")
        key = (code, month.isoformat())
        if key in seen:
            raise ValueError("Mes de funnel duplicado para un proyecto")
        seen.add(key)

        leads = _count(raw["leads"], "leads")
        unique_clients = _count(raw["clientes_unicos"], "clientes_unicos")
        mapped = _count(raw["leads_identidad_mapeada"], "leads_identidad_mapeada")
        ambiguous = _count(raw["leads_identidad_ambigua"], "leads_identidad_ambigua")
        unmatched = _count(raw["leads_identidad_sin_match"], "leads_identidad_sin_match")
        if mapped + ambiguous + unmatched != leads:
            raise ValueError(f"Identidad de leads no concilia: {code} {month}")
        if unique_clients > mapped:
            raise ValueError(f"Clientes únicos exceden leads mapeados: {code} {month}")

        rate = raw["identity_match_rate"]
        expected_rate = (mapped / leads) if leads else None
        if rate is not None:
            rate = float(rate)
            if not 0 <= rate <= 1:
                raise ValueError("identity_match_rate fuera de rango")
            if expected_rate is None or abs(rate - expected_rate) > RATE_TOLERANCE:
                raise ValueError(f"identity_match_rate no concilia: {code} {month}")
        elif expected_rate is not None:
            raise ValueError(f"identity_match_rate faltante: {code} {month}")

        proformas = _count(raw["proformas"], "proformas")
        separations = _optional_count(raw["separaciones"], "separaciones")
        minutas = _optional_count(raw["minutas"], "minutas")
        semantics = str(raw["funnel_semantics"])
        if semantics != "EVENT_MONTH_NOT_COHORT":
            raise ValueError("Semántica de funnel no reconocida")

        item = {
            "month": month.isoformat(),
            "leads": leads,
            "unique_clients": unique_clients,
            "proformas": proformas,
            "separations": separations,
            "minutas": minutas,
            "lead_identity": {
                "mapped_leads": mapped,
                "ambiguous_leads": ambiguous,
                "unmatched_leads": unmatched,
                "match_rate": rate,
            },
            "commercial_cutoff": (
                _day(raw["commercial_cutoff"]).isoformat()
                if raw["commercial_cutoff"] is not None else None
            ),
        }
        project = projects[code]
        project["funnel"].append(item)

        history_row = next((row for row in project["history"] if row["month"] == item["month"]), None)
        if history_row is not None:
            if minutas is not None and minutas != history_row["minutas"]:
                raise ValueError(f"Funnel/minutas no concilia: {code} {month}")
            if separations != history_row["separations"]:
                raise ValueError(f"Funnel/separaciones no concilia: {code} {month}")
            history_row["leads"] = leads
            history_row["unique_clients"] = unique_clients
            history_row["proformas"] = proformas

    for project in projects.values():
        project["funnel"].sort(key=lambda row: row["month"])
        total_leads = sum(row["leads"] for row in project["funnel"])
        total_mapped = sum(row["lead_identity"]["mapped_leads"] for row in project["funnel"])
        project["funnel_meta"] = {
            "status": "AVAILABLE" if project["funnel"] else "UNAVAILABLE",
            "semantics": "EVENT_MONTH_NOT_COHORT",
            "months": len(project["funnel"]),
            "identity_match_rate_weighted": (
                total_mapped / total_leads if total_leads else None
            ),
            "conversion_rates_allowed": False,
        }


def build_packet(
    history_rows: list[dict],
    forecast_rows: list[dict],
    generated_at: str,
    funnel_rows: list[dict] | None = None,
) -> dict:
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
            "forecast_meta": None, "funnel": [], "funnel_meta": None,
        })
        if project["name"] != name:
            raise ValueError("Nombre de proyecto inconsistente")
        project["history"].append({
            "month": month.isoformat(), "source_cutoff": cutoff.isoformat(),
            "stock_open": stock_open, "stock_close": stock_close,
            "minutas": sales, "separations": separations,
            "review_units": _count(raw["unidades_revision"], "unidades_revision"),
            "leads": None, "unique_clients": None, "proformas": None,
            "revenue_pen": None, "margin_pen": None,
        })
    if len(projects) > 5:
        raise ValueError("Máximo cinco proyectos por archivo")

    _attach_funnel(projects, funnel_rows or [])

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
        project["readiness"] = _project_readiness(project, generated_at)
    ready = sum(project["readiness"]["status"] == "READY" for project in projects.values())
    return {
        "contract": "medallio_decision_room_v1", "origin": "MEDALLIO_LOCAL_AGGREGATE",
        "generated_at": generated_at,
        "definitions": {
            "minutas": "ventas_mes de analytics.comercial_proyecto_mes; venta documental gobernada",
            "separations": "separaciones_brutas de analytics.agg_ventas_mensual; otro universo, no tasa de cohorte",
            "stock": "stock reconstruido retrospectivamente; no snapshot histórico as-issued",
            "funnel": "actividad por mes de evento: leads -> clientes únicos -> proformas -> separaciones -> minutas; NO es una cohorte y no autoriza dividir etapas como tasas de conversión",
            "unique_clients": "personas únicas por proyecto y mes entre leads con identidad no ambigua; la cobertura se expone en lead_identity",
            "proformas": "codigo_proforma distintos en proforma_unidad, restringidos al universo residencial gobernado de absorción",
            "forecast": "v_commercial_forecast_monthly; 1–6 meses, pronóstico mensual derivado de horizontes acumulados",
            "readiness": "READY solo si freshness, conciliación stock history↔forecast, quality y horizontes 1–6 pasan",
            "missing": "ingresos, margen y elasticidades no se fabrican; el funnel queda vacío si su contrato no está instalado",
        },
        "readiness_summary": {
            "ready_projects": ready,
            "blocked_projects": len(projects) - ready,
        },
        "projects": list(projects.values()),
    }


def read_source(
    dsn: str | None,
    codes: list[str],
    from_month: date,
) -> tuple[list[dict], list[dict], list[dict]]:
    import psycopg
    from psycopg.rows import dict_row

    if dsn:
        connection = {"conninfo": dsn}
    else:
        from replica_cygnus.settings import load_settings

        cfg = load_settings(Path(__file__).resolve().parents[1], require_source=False).postgres
        connection = {
            "host": cfg.host, "port": cfg.port, "dbname": cfg.database,
            "user": cfg.user, "password": cfg.password, "sslmode": cfg.sslmode,
            "connect_timeout": cfg.connect_timeout,
        }
    with psycopg.connect(**connection, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '30s'")
            cur.execute(HISTORY_SQL, (codes, from_month))
            history = cur.fetchall()

            cur.execute("SELECT to_regclass('analytics.v_commercial_forecast_monthly')")
            forecast = []
            if cur.fetchone()["to_regclass"] is not None:
                cur.execute(FORECAST_SQL, (codes,))
                forecast = cur.fetchall()

            cur.execute("SELECT to_regclass('analytics.v_decision_room_funnel_monthly')")
            funnel = []
            if cur.fetchone()["to_regclass"] is not None:
                cur.execute(FUNNEL_SQL, (codes, from_month))
                funnel = cur.fetchall()
    return history, forecast, funnel


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
    dsn = os.getenv("MEDALLIO_DSN")  # opcional: por defecto usa POSTGRES_* del .env habitual
    history, forecast, funnel = read_source(dsn, args.project, date.fromisoformat(args.from_month))
    packet = build_packet(
        history,
        forecast,
        datetime.now(timezone.utc).isoformat(),
        funnel_rows=funnel,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(packet, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(
        f"Archivo generado: {args.output} | proyectos={len(packet['projects'])} | "
        f"ready={packet['readiness_summary']['ready_projects']} | "
        f"blocked={packet['readiness_summary']['blocked_projects']} | "
        f"funnel_rows={sum(len(p['funnel']) for p in packet['projects'])} | "
        f"filas={sum(len(p['history']) for p in packet['projects'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
