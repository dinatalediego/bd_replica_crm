from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from replica_cygnus.stock_export.service import _connect


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQL_PATH = ROOT / "sql" / "60_monthly_stock_movement" / "00_monthly_stock_movement.sql"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "movimiento_stock_mensual"

REQUIRED_RELATIONS = [
    "core.dim_unidad",
    "core.dim_proyecto",
    "analytics.fact_movimientos_stock",
    "analytics.fact_stock_ofertado_diario_tipo",
    "analytics.dim_unidad_semantica",
    "analytics.v_stock_coverage_actual_por_tipo",
    "analytics.stock_discount_rules",
]

MONTH_NAMES_ES = {
    1: "ENERO",
    2: "FEBRERO",
    3: "MARZO",
    4: "ABRIL",
    5: "MAYO",
    6: "JUNIO",
    7: "JULIO",
    8: "AGOSTO",
    9: "SETIEMBRE",
    10: "OCTUBRE",
    11: "NOVIEMBRE",
    12: "DICIEMBRE",
}


def _query_df(sql: str, params: list[object] | None = None) -> pd.DataFrame:
    with _connect() as conn:
        with conn.cursor() as cur:
            if params is None:
                cur.execute(sql)
            else:
                cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def validate_monthly_stock_dependencies() -> None:
    missing: list[str] = []
    with _connect() as conn:
        with conn.cursor() as cur:
            for relation in REQUIRED_RELATIONS:
                cur.execute("SELECT to_regclass(%s)", [relation])
                if cur.fetchone()[0] is None:
                    missing.append(relation)

    if missing:
        joined = "\n - ".join(missing)
        raise RuntimeError(
            "Faltan dependencias del contrato de absorción/stock en Medallio DW:\n"
            f" - {joined}\n"
            "No se fabricará historia ni se reconstruirá el DW automáticamente. "
            "Instala/actualiza primero la capa de absorción v1.1 ya existente en el repositorio."
        )


def install_monthly_stock_sql(sql_path: Path = DEFAULT_SQL_PATH) -> None:
    validate_monthly_stock_dependencies()
    sql = sql_path.read_text(encoding="utf-8")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def _period_start(period: str | date | None) -> date:
    if period is None:
        today = date.today()
        return date(today.year, today.month, 1)
    if isinstance(period, date):
        return date(period.year, period.month, 1)
    text = str(period).strip()
    parsed = pd.to_datetime(text, format="%Y-%m", errors="raise")
    return date(parsed.year, parsed.month, 1)


def _project_clause(projects: Iterable[str] | None) -> tuple[str, list[object]]:
    if not projects:
        return "", []
    clean = [str(p).strip() for p in projects if str(p).strip()]
    if not clean:
        return "", []
    placeholders = ", ".join(["%s"] * len(clean))
    return f" AND proyecto IN ({placeholders})", clean


def fetch_month_summary(period: str | date | None, projects: Iterable[str] | None = None) -> pd.DataFrame:
    month = _period_start(period)
    project_where, project_params = _project_clause(projects)
    sql = f"""
        SELECT *
        FROM analytics.v_stock_movimiento_mensual_export
        WHERE periodo_mes = %s
        {project_where}
        ORDER BY proyecto
    """
    return _query_df(sql, [month, *project_params])


def fetch_month_movements(period: str | date | None, projects: Iterable[str] | None = None) -> pd.DataFrame:
    month = _period_start(period)
    project_where, project_params = _project_clause(projects)
    sql = f"""
        SELECT
            periodo_mes,
            codigo_proyecto,
            proyecto,
            unidad,
            tipo_unidad,
            piso,
            area_total,
            movimiento,
            fecha_evento,
            codigo_proforma,
            estado_actual,
            precio_lista,
            discount_pct,
            precio_con_descuento,
            precio_venta_actual,
            moneda,
            source_table,
            source_id,
            transition_reason,
            event_rank
        FROM analytics.v_stock_movimiento_mensual_unidad_export
        WHERE periodo_mes = %s
        {project_where}
        ORDER BY proyecto, fecha_evento, unidad, movimiento
    """
    return _query_df(sql, [month, *project_params])


def _safe_sheet_name(name: str) -> str:
    forbidden = "[]:*?/\\"
    clean = "".join("_" if c in forbidden else c for c in name)
    return clean[:31] or "Proyecto"


def _money_format(currency: str) -> str:
    return '"S/ "#,##0.00' if str(currency).upper() in {"PEN", "SOLES", "S/"} else '"US$ "#,##0.00'


def _write_title(worksheet, workbook, end_col: int, title: str, generated_at: datetime) -> None:
    title_fmt = workbook.add_format({
        "bold": True,
        "font_size": 17,
        "font_color": "#FFFFFF",
        "bg_color": "#1F5E43",
        "align": "left",
        "valign": "vcenter",
        "top": 2,
        "top_color": "#2ECC71",
    })
    subtitle_fmt = workbook.add_format({
        "font_size": 10,
        "font_color": "#4F4F4F",
        "italic": True,
    })
    worksheet.merge_range(0, 0, 0, end_col, title, title_fmt)
    worksheet.write(1, 0, f"Actualizado al {generated_at:%d/%m/%Y}", subtitle_fmt)
    worksheet.set_row(0, 30)


def _write_summary_sheet(writer: pd.ExcelWriter, summary: pd.DataFrame, period: date, generated_at: datetime) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet("RESUMEN")
    writer.sheets["RESUMEN"] = worksheet

    month_name = MONTH_NAMES_ES[period.month]
    prev_month_end = pd.Timestamp(period) - pd.Timedelta(days=1)

    _write_title(
        worksheet,
        workbook,
        6,
        f"MOVIMIENTO DE STOCK · RESUMEN EJECUTIVO · {month_name} {period.year}",
        generated_at,
    )

    header_fmt = workbook.add_format({
        "bold": True,
        "font_color": "#1B2230",
        "bg_color": "#C6E0B4",
        "border": 1,
        "border_color": "#55B878",
        "align": "center",
        "valign": "vcenter",
        "text_wrap": True,
    })
    text_fmt = workbook.add_format({"border": 1, "border_color": "#E0E5E8"})
    int_fmt = workbook.add_format({
        "border": 1,
        "border_color": "#E0E5E8",
        "num_format": "0",
        "align": "center",
    })
    pct_fmt = workbook.add_format({
        "border": 1,
        "border_color": "#E0E5E8",
        "num_format": "0.0%",
        "align": "center",
    })

    headers = [
        "PROYECTO",
        f"STOCK AL {prev_month_end:%d-%m-%y}",
        f"MOVIMIENTO NETO DE {month_name}",
        f"VENDIDAS / MINUTAS {month_name}",
        "SALDO FINAL",
        f"ABSORCIÓN NETA % {month_name}-{str(period.year)[-2:]}",
        "ABSORCIÓN NETA ÚLTIMOS 6 MESES",
    ]
    start_row = 4
    for c, h in enumerate(headers):
        worksheet.write(start_row, c, h, header_fmt)

    for r, (_, row) in enumerate(summary.iterrows(), start=start_row + 1):
        worksheet.write(r, 0, row["proyecto"], text_fmt)
        worksheet.write(r, 1, row["stock_inicio_observado"], int_fmt)
        worksheet.write(r, 2, row["movimiento_neto_mes"], int_fmt)
        worksheet.write(r, 3, row["ventas_minutas_mes"], int_fmt)
        worksheet.write(r, 4, row["saldo_final_observado"], int_fmt)
        if pd.isna(row["absorcion_neta_mes"]):
            worksheet.write_blank(r, 5, None, pct_fmt)
        else:
            worksheet.write(r, 5, row["absorcion_neta_mes"], pct_fmt)
        if pd.isna(row["absorcion_neta_6m"]):
            worksheet.write_blank(r, 6, None, pct_fmt)
        else:
            worksheet.write(r, 6, row["absorcion_neta_6m"], pct_fmt)

    worksheet.freeze_panes(start_row + 1, 1)
    worksheet.set_column("A:A", 24)
    worksheet.set_column("B:E", 20)
    worksheet.set_column("F:G", 29)
    worksheet.set_row(start_row, 36)
    worksheet.hide_gridlines(2)


def _write_project_sheet(
    writer: pd.ExcelWriter,
    project: str,
    summary_row: pd.Series,
    movements: pd.DataFrame,
    period: date,
    generated_at: datetime,
) -> None:
    workbook = writer.book
    sheet_name = _safe_sheet_name(project.upper())
    worksheet = workbook.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = worksheet

    month_name = MONTH_NAMES_ES[period.month]
    _write_title(
        worksheet,
        workbook,
        8,
        f"MOVIMIENTO DE STOCK · {project} · {month_name} {period.year}",
        generated_at,
    )

    kpi_label = workbook.add_format({
        "bold": True,
        "font_color": "#50606D",
        "font_size": 9,
        "bg_color": "#F4F7F5",
        "border": 1,
        "border_color": "#D9E2DC",
        "align": "center",
    })
    kpi_value = workbook.add_format({
        "bold": True,
        "font_size": 16,
        "font_color": "#0A2F43",
        "bg_color": "#FFFFFF",
        "border": 1,
        "border_color": "#D9E2DC",
        "align": "center",
    })
    kpi_pct = workbook.add_format({
        "bold": True,
        "font_size": 16,
        "font_color": "#0A2F43",
        "bg_color": "#FFFFFF",
        "border": 1,
        "border_color": "#D9E2DC",
        "align": "center",
        "num_format": "0.0%",
    })

    kpis = [
        ("STOCK INICIO", summary_row["stock_inicio_observado"], False),
        ("MOV. NETO", summary_row["movimiento_neto_mes"], False),
        ("VENDIDAS / MINUTAS", summary_row["ventas_minutas_mes"], False),
        ("SALDO FINAL", summary_row["saldo_final_observado"], False),
        ("ABSORCIÓN NETA", summary_row["absorcion_neta_mes"], True),
    ]
    for idx, (label, value, is_pct) in enumerate(kpis):
        c0 = idx * 2
        worksheet.merge_range(3, c0, 3, c0 + 1, label, kpi_label)
        if pd.isna(value):
            worksheet.merge_range(4, c0, 4, c0 + 1, "", kpi_value)
        else:
            worksheet.merge_range(4, c0, 4, c0 + 1, value, kpi_pct if is_pct else kpi_value)

    header_fmt = workbook.add_format({
        "bold": True,
        "font_color": "#1B2230",
        "bg_color": "#C6E0B4",
        "border": 1,
        "border_color": "#55B878",
        "align": "center",
        "valign": "vcenter",
        "text_wrap": True,
    })
    text_fmt = workbook.add_format({"border": 1, "border_color": "#E0E5E8"})
    center_fmt = workbook.add_format({
        "border": 1,
        "border_color": "#E0E5E8",
        "align": "center",
    })
    date_fmt = workbook.add_format({
        "border": 1,
        "border_color": "#E0E5E8",
        "num_format": "dd/mm/yyyy",
        "align": "center",
    })
    pct_fmt = workbook.add_format({
        "border": 1,
        "border_color": "#E0E5E8",
        "num_format": "0%",
        "align": "center",
    })
    movement_formats = {
        "SEPARACION": workbook.add_format({"border": 1, "border_color": "#E0E5E8", "bg_color": "#FCE4D6", "align": "center"}),
        "CAIDA": workbook.add_format({"border": 1, "border_color": "#E0E5E8", "bg_color": "#F4CCCC", "align": "center"}),
        "VENTA": workbook.add_format({"border": 1, "border_color": "#E0E5E8", "bg_color": "#D9EAD3", "align": "center"}),
    }

    currency = movements["moneda"].mode().iat[0] if not movements.empty and not movements["moneda"].mode().empty else "PEN"
    money_fmt = workbook.add_format({
        "border": 1,
        "border_color": "#E0E5E8",
        "num_format": _money_format(currency),
    })

    headers = [
        "MOVIMIENTO",
        "FECHA",
        "UNIDAD",
        "ESTADO ACTUAL",
        "PISO",
        "ÁREA M²",
        "PRECIO LISTA",
        "DSCTO.",
        "PRECIO CON DESCUENTO",
    ]
    start_row = 7
    for c, h in enumerate(headers):
        worksheet.write(start_row, c, h, header_fmt)

    for r, (_, row) in enumerate(movements.iterrows(), start=start_row + 1):
        move = str(row.get("movimiento", ""))
        worksheet.write(r, 0, move, movement_formats.get(move, center_fmt))
        fecha_evento = row.get("fecha_evento")
        if pd.isna(fecha_evento):
            worksheet.write_blank(r, 1, None, date_fmt)
        else:
            worksheet.write_datetime(r, 1, pd.Timestamp(fecha_evento).to_pydatetime(), date_fmt)
        worksheet.write(r, 2, row.get("unidad", ""), text_fmt)
        worksheet.write(r, 3, row.get("estado_actual", ""), text_fmt)
        worksheet.write(r, 4, row.get("piso", ""), center_fmt)
        worksheet.write(r, 5, row.get("area_total", ""), center_fmt)
        worksheet.write(r, 6, row.get("precio_lista", ""), money_fmt)
        worksheet.write(r, 7, row.get("discount_pct", ""), pct_fmt)
        worksheet.write(r, 8, row.get("precio_con_descuento", ""), money_fmt)

    last_row = start_row + max(len(movements), 1)
    worksheet.autofilter(start_row, 0, last_row, len(headers) - 1)
    worksheet.freeze_panes(start_row + 1, 3)
    worksheet.set_row(start_row, 30)
    worksheet.set_column("A:A", 16)
    worksheet.set_column("B:B", 13)
    worksheet.set_column("C:C", 15)
    worksheet.set_column("D:D", 18)
    worksheet.set_column("E:E", 9)
    worksheet.set_column("F:F", 12)
    worksheet.set_column("G:G", 18)
    worksheet.set_column("H:H", 10)
    worksheet.set_column("I:I", 22)
    worksheet.hide_gridlines(2)


def _write_control_sheet(writer: pd.ExcelWriter, summary: pd.DataFrame, period: date, generated_at: datetime) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet("CONTROL")
    writer.sheets["CONTROL"] = worksheet

    _write_title(
        worksheet,
        workbook,
        7,
        f"CONTROL DE EVIDENCIA · {MONTH_NAMES_ES[period.month]} {period.year}",
        generated_at,
    )

    header_fmt = workbook.add_format({
        "bold": True,
        "font_color": "#FFFFFF",
        "bg_color": "#315A49",
        "border": 1,
        "align": "center",
        "text_wrap": True,
    })
    body_fmt = workbook.add_format({"border": 1, "border_color": "#E0E5E8"})
    pct_fmt = workbook.add_format({
        "border": 1,
        "border_color": "#E0E5E8",
        "num_format": "0.0%",
        "align": "center",
    })

    headers = [
        "PROYECTO",
        "PRIMERA FECHA OBSERVADA",
        "ÚLTIMA FECHA OBSERVADA",
        "COBERTURA STOCK ACTUAL",
        "GAP STOCK DISPONIBLE",
        "CALIDAD",
        "MÉTODO STOCK HISTÓRICO",
        "MÉTODO MOVIMIENTO",
    ]
    start_row = 4
    for c, h in enumerate(headers):
        worksheet.write(start_row, c, h, header_fmt)

    for r, (_, row) in enumerate(summary.iterrows(), start=start_row + 1):
        worksheet.write(r, 0, row["proyecto"], body_fmt)
        worksheet.write(r, 1, str(row["primera_fecha_observada"]), body_fmt)
        worksheet.write(r, 2, str(row["ultima_fecha_observada"]), body_fmt)
        if pd.isna(row["cobertura_stock_disponible_ratio"]):
            worksheet.write_blank(r, 3, None, pct_fmt)
        else:
            worksheet.write(r, 3, row["cobertura_stock_disponible_ratio"], pct_fmt)
        worksheet.write(r, 4, row["gap_stock_disponible"], body_fmt)
        worksheet.write(r, 5, row["calidad_stock_historico"], body_fmt)
        worksheet.write(r, 6, row["metodo_stock_historico"], body_fmt)
        worksheet.write(r, 7, row["metodo_movimiento"], body_fmt)

    worksheet.write(start_row + len(summary) + 3, 0, "Contrato", header_fmt)
    worksheet.merge_range(
        start_row + len(summary) + 3,
        1,
        start_row + len(summary) + 3,
        7,
        "Absorción principal = departamentos. Movimiento neto = separaciones efectivas - caídas efectivas. "
        "Ventas/minutas se muestran aparte. El stock histórico es observado por ledger; el stock actual certificado vive en snapshots.",
        body_fmt,
    )

    worksheet.set_column("A:A", 24)
    worksheet.set_column("B:C", 22)
    worksheet.set_column("D:E", 20)
    worksheet.set_column("F:H", 34)
    worksheet.hide_gridlines(2)


def export_monthly_stock_excel(
    period: str | date | None = None,
    projects: Iterable[str] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    month = _period_start(period)
    summary = fetch_month_summary(month, projects)
    if summary.empty:
        raise RuntimeError(
            f"No hay datos de movimiento mensual para {month:%Y-%m} con los filtros solicitados."
        )

    movements = fetch_month_movements(month, projects)
    generated_at = datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"Movimiento_Stock_{month:%Y_%m}.xlsx"

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        _write_summary_sheet(writer, summary, month, generated_at)
        for _, row in summary.iterrows():
            project = str(row["proyecto"])
            project_moves = movements[movements["proyecto"] == project].copy()
            _write_project_sheet(writer, project, row, project_moves, month, generated_at)
        _write_control_sheet(writer, summary, month, generated_at)

    return output_path
