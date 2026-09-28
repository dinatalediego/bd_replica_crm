from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings

NAVY = "#17324D"
TEAL = "#1F7A8C"
GREEN = "#2E7D32"
AMBER = "#E5A93B"
RED = "#B42318"
LIGHT_BLUE = "#EAF2F8"
LIGHT_GREEN = "#EAF6EC"
LIGHT_AMBER = "#FFF4D6"
LIGHT_GRAY = "#F5F7FA"
WHITE = "#FFFFFF"
DARK = "#243447"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera Excel ejecutivo de conversión comercial por medio de captación."
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--medio", default="all", help="Ej. urbania o 'all'.")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def _fetch_df(conn, sql: str, params: tuple[Any, ...]) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [desc.name for desc in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def _where_medio(medio: str, column: str = "medio_captacion") -> tuple[str, tuple[Any, ...]]:
    if medio.strip().lower() == "all":
        return "", ()
    return f" AND lower(btrim({column})) = %s", (medio.strip().lower(),)


def _load_frames(conn, year: int, medio: str) -> dict[str, pd.DataFrame]:
    extra, params = _where_medio(medio)
    export = _fetch_df(
        conn,
        f"""
        SELECT *
        FROM analytics.v_portal_conversion_export
        WHERE lead_year = %s {extra}
        ORDER BY fecha_creacion DESC, lead_uid
        """,
        (year, *params),
    )
    summary = _fetch_df(
        conn,
        f"""
        SELECT *
        FROM analytics.v_portal_conversion_medio_total
        WHERE lead_year = %s {extra}
        ORDER BY tasa_conversion DESC NULLS LAST, leads DESC, medio_captacion
        """,
        (year, *params),
    )
    by_source = _fetch_df(
        conn,
        f"""
        SELECT *
        FROM analytics.v_portal_conversion_medio
        WHERE lead_year = %s {extra}
        ORDER BY medio_captacion, fuente_lead
        """,
        (year, *params),
    )
    cohorts = _fetch_df(
        conn,
        f"""
        SELECT *
        FROM analytics.v_portal_conversion_cohorte_mensual
        WHERE extract(year FROM mes_lead)::integer = %s {extra}
        ORDER BY mes_lead, medio_captacion, fuente_lead
        """,
        (year, *params),
    )
    projects = _fetch_df(
        conn,
        f"""
        SELECT *
        FROM analytics.v_portal_conversion_proyecto
        WHERE lead_year = %s {extra}
        ORDER BY medio_captacion, conversiones DESC, leads DESC, codigo_proyecto
        """,
        (year, *params),
    )
    conv_extra, conv_params = _where_medio(medio, "medio_atribuido")
    conversions = _fetch_df(
        conn,
        f"""
        SELECT *
        FROM analytics.v_portal_conversion_conversiones
        WHERE fecha_lead_atribuido >= %s
          AND fecha_lead_atribuido < %s
          {conv_extra}
        ORDER BY fecha_separacion DESC, conversion_key
        """,
        (datetime(year, 1, 1), datetime(year + 1, 1, 1), *conv_params),
    )
    health = _fetch_df(conn, "SELECT * FROM analytics.v_portal_conversion_health", ())
    return {
        "export": export,
        "summary": summary,
        "by_source": by_source,
        "cohorts": cohorts,
        "projects": projects,
        "conversions": conversions,
        "health": health,
    }


def _formats(workbook):
    return {
        "title": workbook.add_format({
            "bold": True, "font_size": 20, "font_color": WHITE,
            "bg_color": NAVY, "align": "left", "valign": "vcenter",
        }),
        "subtitle": workbook.add_format({"font_size": 10, "font_color": "#5C6B7A", "italic": True}),
        "section": workbook.add_format({"bold": True, "font_size": 12, "font_color": WHITE, "bg_color": TEAL}),
        "header": workbook.add_format({
            "bold": True, "font_color": WHITE, "bg_color": NAVY,
            "align": "center", "valign": "vcenter", "text_wrap": True,
        }),
        "kpi_label": workbook.add_format({
            "bold": True, "font_color": DARK, "bg_color": LIGHT_BLUE,
            "border": 1, "border_color": "#D9E2EC",
        }),
        "kpi_value": workbook.add_format({
            "bold": True, "font_size": 16, "font_color": NAVY,
            "border": 1, "border_color": "#D9E2EC", "align": "center",
        }),
        "percent": workbook.add_format({"num_format": "0.00%"}),
        "decimal": workbook.add_format({"num_format": "0.00"}),
        "integer": workbook.add_format({"num_format": "0"}),
        "date": workbook.add_format({"num_format": "dd/mm/yyyy"}),
        "datetime": workbook.add_format({"num_format": "dd/mm/yyyy hh:mm"}),
        "note": workbook.add_format({"font_color": "#44546A", "bg_color": LIGHT_GRAY, "text_wrap": True, "valign": "top"}),
        "good": workbook.add_format({"bg_color": LIGHT_GREEN, "font_color": GREEN}),
        "warn": workbook.add_format({"bg_color": LIGHT_AMBER, "font_color": "#8A5A00"}),
        "bad": workbook.add_format({"bg_color": "#FDECEC", "font_color": RED}),
    }


def _write_df(writer, df: pd.DataFrame, sheet_name: str) -> None:
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    ws = writer.sheets[sheet_name]
    fmt = _formats(writer.book)
    if not df.empty:
        ws.set_row(0, 30, fmt["header"])
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)
    ws.freeze_panes(1, 5)

    for idx, col in enumerate(df.columns):
        values = df[col].astype(str).replace("nan", "") if not df.empty else pd.Series(dtype=str)
        sample_width = max([len(str(col))] + [min(len(v), 45) for v in values.head(200).tolist()])
        width = min(max(sample_width + 2, 11), 34)
        low = col.lower()
        cell_fmt = None
        if "fecha" in low or low.endswith("_at"):
            cell_fmt, width = fmt["datetime"], max(width, 18)
        elif "tasa" in low:
            cell_fmt, width = fmt["percent"], max(width, 13)
        elif low.startswith("score_") or "dias_" in low:
            cell_fmt = fmt["decimal"]
        ws.set_column(idx, idx, width, cell_fmt)

    if "estado_match" in df.columns and not df.empty:
        col = df.columns.get_loc("estado_match")
        ws.conditional_format(1, col, len(df), col, {
            "type": "text", "criteria": "containing", "value": "CONFIRMADO", "format": fmt["good"]
        })
        ws.conditional_format(1, col, len(df), col, {
            "type": "text", "criteria": "containing", "value": "PROBABLE", "format": fmt["good"]
        })
        ws.conditional_format(1, col, len(df), col, {
            "type": "text", "criteria": "containing", "value": "REVISAR", "format": fmt["warn"]
        })


def _dashboard(writer, frames: dict[str, pd.DataFrame], year: int, medio: str) -> None:
    wb = writer.book
    ws = wb.add_worksheet("Dashboard")
    writer.sheets["Dashboard"] = ws
    fmt = _formats(wb)
    selected = "Todos los medios" if medio.lower() == "all" else medio.title()

    ws.set_column("A:A", 32)
    ws.set_column("B:B", 18)
    ws.set_column("C:C", 4)
    ws.set_column("D:J", 16)
    ws.set_row(0, 34)
    ws.merge_range("A1:J1", f"Conversión comercial de leads — {selected} — {year}", fmt["title"])
    ws.write(
        "A2",
        "Medallio: conversión = Separación Activo; comprador deduplicado por DNI cuando existe DNI válido.",
        fmt["subtitle"],
    )

    detail = frames["export"]
    if detail.empty:
        included = detail
    else:
        included = detail[detail["incluir_en_kpi"].fillna(False)]

    leads = len(included)
    conversions = int(included["conversion_atribuida"].fillna(False).sum()) if not included.empty else 0
    rate = conversions / leads if leads else 0.0
    avg_days = (
        pd.to_numeric(
            included.loc[included["conversion_atribuida"].fillna(False), "dias_a_separacion"],
            errors="coerce",
        ).mean()
        if not included.empty
        else float("nan")
    )
    duplicates = int(detail["duplicado_en_origen"].fillna(False).sum()) if not detail.empty else 0
    review = int((detail["estado_match"] == "REVISAR").sum()) if not detail.empty else 0

    kpis = [
        ("Leads incluidos", int(leads), fmt["integer"]),
        ("Conversiones únicas", conversions, fmt["integer"]),
        ("Tasa de conversión", rate, fmt["percent"]),
        ("Días prom. lead → separación", None if pd.isna(avg_days) else float(avg_days), fmt["decimal"]),
        ("Medio actual excluido por ORIGEN", duplicates, fmt["integer"]),
        ("Matches a revisar", review, fmt["integer"]),
    ]
    row = 4
    for label, value, value_fmt in kpis:
        ws.write(row, 0, label, fmt["kpi_label"])
        if value is None:
            ws.write(row, 1, "—", fmt["kpi_value"])
        else:
            ws.write(row, 1, value, value_fmt)
        row += 1

    ws.merge_range("D4:J4", "Resumen por medio", fmt["section"])
    summary = frames["summary"].copy()
    if summary.empty:
        ws.write("D6", "Sin datos para el filtro seleccionado.", fmt["note"])
    else:
        display = summary[[
            "medio_captacion", "leads", "conversiones", "tasa_conversion",
            "dias_promedio_separacion", "duplicados_origen_excluidos",
        ]].rename(columns={
            "medio_captacion": "Medio",
            "leads": "Leads",
            "conversiones": "Conversiones",
            "tasa_conversion": "Tasa",
            "dias_promedio_separacion": "Días prom.",
            "duplicados_origen_excluidos": "Dup. ORIGEN",
        })
        start = 5
        for c, col in enumerate(display.columns):
            ws.write(start, 3 + c, col, fmt["header"])
        for r, values in enumerate(display.itertuples(index=False, name=None), start=start + 1):
            for c, value in enumerate(values):
                cell_fmt = fmt["percent"] if c == 3 else (fmt["decimal"] if c == 4 else None)
                ws.write(r, 3 + c, value, cell_fmt)
        ws.autofilter(start, 3, start + len(display), 3 + len(display.columns) - 1)
        ws.set_column(3, 3, 20)
        ws.set_column(4, 8, 14)

        if len(display) >= 2:
            chart = wb.add_chart({"type": "column"})
            chart.add_series({
                "name": "Tasa de conversión",
                "categories": ["Dashboard", start + 1, 3, start + len(display), 3],
                "values": ["Dashboard", start + 1, 6, start + len(display), 6],
                "data_labels": {"value": True, "num_format": "0.0%"},
            })
            chart.set_title({"name": "Conversión por medio"})
            chart.set_y_axis({"num_format": "0.0%"})
            chart.set_legend({"none": True})
            chart.set_style(10)
            ws.insert_chart("D18", chart, {"x_scale": 1.3, "y_scale": 1.15})

    ws.merge_range("A13:B13", "Reglas de control", fmt["section"])
    notes = [
        "DNI: solo 8 dígitos exactos; AUTO-* nunca se trata como DNI.",
        "Nombre, celular y email: similitud fuzzy; nombre por sí solo no convierte.",
        "Gate temporal: la separación debe ocurrir después del lead.",
        "Una conversión se cuenta una sola vez por persona; DNI es la llave prioritaria.",
        "Si el mismo lead está en ORIGEN y MEDIO_ACTUAL, ORIGEN gana; MEDIO_ACTUAL queda auditado fuera del KPI.",
    ]
    for r, note in enumerate(notes, start=14):
        ws.merge_range(r - 1, 0, r - 1, 1, note, fmt["note"])
        ws.set_row(r - 1, 31)
    ws.freeze_panes(3, 0)


def _cohorts(writer, frames: dict[str, pd.DataFrame]) -> None:
    wb = writer.book
    fmt = _formats(wb)
    cohorts = frames["cohorts"]
    projects = frames["projects"]
    cohorts.to_excel(writer, sheet_name="Cohortes", index=False, startrow=2)
    ws = writer.sheets["Cohortes"]
    max_cols = max(1, len(cohorts.columns), len(projects.columns))
    ws.merge_range(0, 0, 0, max_cols - 1, "Cohortes mensuales", fmt["title"])
    if not cohorts.empty:
        ws.set_row(2, 30, fmt["header"])
        ws.autofilter(2, 0, 2 + len(cohorts), len(cohorts.columns) - 1)
    start = 5 + len(cohorts)
    ws.merge_range(start, 0, start, max_cols - 1, "Conversión por proyecto", fmt["section"])
    projects.to_excel(writer, sheet_name="Cohortes", index=False, startrow=start + 2)
    if not projects.empty:
        ws.set_row(start + 2, 30, fmt["header"])
    for c in range(max_cols):
        ws.set_column(c, c, 18)
    ws.freeze_panes(3, 0)


def _methodology(writer) -> None:
    wb = writer.book
    ws = wb.add_worksheet("Metodologia")
    writer.sheets["Metodologia"] = ws
    fmt = _formats(wb)
    ws.set_column("A:A", 28)
    ws.set_column("B:B", 95)
    ws.merge_range("A1:B1", "Metodología de atribución", fmt["title"])
    rows = [
        ("ORIGEN", "raw_cygnus.clientes_proyectos desde 2026; fuente prioritaria de adquisición."),
        ("MEDIO_ACTUAL", "raw_cygnus.interacciones con nombre = 'portal inmobiliario'."),
        ("Comprador", "raw_cygnus.procesos: nombre='Separacion' y estado='Activo'; identidad enriquecida desde clientes."),
        ("Deduplicación", "Una persona convertida cuenta una vez. DNI exacto de 8 dígitos tiene prioridad."),
        ("Prioridad", "El mismo lead en ORIGEN y MEDIO_ACTUAL se atribuye a ORIGEN."),
        ("DNI", "Exactamente 8 dígitos iguales; AUTO-* no es DNI."),
        ("Nombre", "Tildes/mayúsculas/puntuación normalizadas y score fuzzy."),
        ("Celular", "Dígitos y +51 normalizados; comparación exacta/fuzzy controlada."),
        ("Email", "Minúsculas/espacios normalizados; comparación fuzzy con control de dominio."),
        ("CONFIRMADO", "DNI exacto o contacto casi exacto corroborado."),
        ("PROBABLE", "Dos evidencias consistentes; sí entra al KPI automático."),
        ("REVISAR", "Evidencia parcial; no entra al KPI automático."),
        ("Temporalidad", "fecha_separacion >= fecha_creacion."),
        ("Granularidad", "Leads en denominador; conversiones únicas atribuidas en numerador."),
    ]
    ws.write_row("A3", ["Concepto", "Regla"], fmt["header"])
    for idx, row in enumerate(rows, start=3):
        ws.write(idx, 0, row[0])
        ws.write(idx, 1, row[1], fmt["note"])
        ws.set_row(idx, 36)
    ws.freeze_panes(3, 0)


def build_workbook(frames: dict[str, pd.DataFrame], output: Path, year: int, medio: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(
        output,
        engine="xlsxwriter",
        datetime_format="dd/mm/yyyy hh:mm",
        date_format="dd/mm/yyyy",
    ) as writer:
        _dashboard(writer, frames, year, medio)
        _cohorts(writer, frames)
        detail = frames["export"]
        origin = detail[detail["fuente_lead"] == "ORIGEN"].copy() if not detail.empty else detail.copy()
        current = detail[detail["fuente_lead"] == "MEDIO_ACTUAL"].copy() if not detail.empty else detail.copy()
        _write_df(writer, origin, "Match_Origen")
        _write_df(writer, current, "Match_Medio_Actual")
        _write_df(writer, frames["conversions"], "Conversiones")
        _methodology(writer)


def main() -> int:
    args = parse_args()
    settings = load_settings()
    slug = "todos" if args.medio.lower() == "all" else args.medio.lower().replace(" ", "_")
    output = (
        Path(args.output)
        if args.output
        else Path(settings.project_root) / "reports" / f"portal_conversion_{slug}_{args.year}.xlsx"
    )
    with connect_postgres(settings) as conn:
        frames = _load_frames(conn, args.year, args.medio)
    build_workbook(frames, output, args.year, args.medio)
    print(f"[PORTAL_CONVERSION] Excel generado: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
