from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from replica_cygnus.stock_export.service import _connect


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQL_PATH = ROOT / "sql" / "60_monthly_stock_movement" / "00_monthly_stock_movement.sql"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "movimiento_stock_mensual"

# Dependencias mínimas, no destructivas, necesarias para reconstruir el
# histórico OBSERVADO directamente desde el ledger existente.
REQUIRED_RELATIONS = [
    "core.dim_unidad",
    "core.dim_proyecto",
    "analytics.fact_movimientos_stock",
    "analytics.stock_discount_rules",
]

# Evidencia complementaria: mejora CONTROL si existe, pero nunca bloquea el
# reporte ni se crea/reconstruye automáticamente.
OPTIONAL_COVERAGE_RELATION = "analytics.v_stock_coverage_actual_por_tipo"

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


def _relation_exists(relation: str) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", [relation])
            return cur.fetchone()[0] is not None


def validate_monthly_stock_dependencies() -> None:
    """Valida sólo el contrato mínimo que el reporte realmente necesita.

    No instala Phase C, no ejecuta TRUNCATE y no fabrica snapshots históricos.
    `fact_movimientos_stock` + `core.dim_unidad` son suficientes para derivar el
    stock observado y los movimientos mensuales de departamentos.
    """
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
            "Faltan dependencias mínimas para el reporte mensual en Medallio DW:\n"
            f" - {joined}\n"
            "El módulo no modificará hechos históricos ni reconstruirá el DW automáticamente."
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
    parsed = pd.to_datetime(str(period).strip(), format="%Y-%m", errors="raise")
    return date(parsed.year, parsed.month, 1)


def _project_clause(projects: Iterable[str] | None) -> tuple[str, list[object]]:
    if not projects:
        return "", []
    clean = [str(p).strip() for p in projects if str(p).strip()]
    if not clean:
        return "", []
    placeholders = ", ".join(["%s"] * len(clean))
    return f" AND proyecto IN ({placeholders})", clean


def _attach_optional_coverage(summary: pd.DataFrame) -> pd.DataFrame:
    """Añade reconciliación actual sólo si el contrato v1.1 está instalado."""
    out = summary.copy()

    # Defaults explícitos: el histórico sigue siendo válido como ledger
    # observado aunque no exista snapshot certificado en esta instalación.
    out["stock_disponible_actual"] = pd.NA
    out["stock_disponible_ledger"] = pd.NA
    out["gap_stock_disponible"] = pd.NA
    out["cobertura_stock_disponible_ratio"] = pd.NA
    out["ledger_reconcilia_estado_actual"] = pd.NA
    out["calidad_stock_historico"] = "HISTORICO_LEDGER_OBSERVADO_SIN_SNAPSHOT_CERTIFICADO"

    if not _relation_exists(OPTIONAL_COVERAGE_RELATION):
        return out

    coverage = _query_df(
        """
        SELECT
            codigo_proyecto,
            stock_disponible_actual,
            stock_disponible_ledger,
            gap_stock_disponible,
            cobertura_stock_disponible_ratio,
            ledger_reconcilia_estado_actual
        FROM analytics.v_stock_coverage_actual_por_tipo
        WHERE tipo_unidad_consolidado = 'DEPARTAMENTO'
        """
    )
    if coverage.empty:
        return out

    base_cols = [
        "stock_disponible_actual",
        "stock_disponible_ledger",
        "gap_stock_disponible",
        "cobertura_stock_disponible_ratio",
        "ledger_reconcilia_estado_actual",
    ]
    out = out.drop(columns=base_cols, errors="ignore").merge(
        coverage,
        how="left",
        on="codigo_proyecto",
    )

    def quality(row: pd.Series) -> str:
        value = row.get("ledger_reconcilia_estado_actual")
        if pd.isna(value):
            return "HISTORICO_LEDGER_OBSERVADO_SIN_COBERTURA"
        return (
            "CERTIFICADO_ESTADO_ACTUAL"
            if bool(value)
            else "HISTORICO_LEDGER_CON_GAP_DE_COBERTURA"
        )

    out["calidad_stock_historico"] = out.apply(quality, axis=1)
    return out


def fetch_month_summary(
    period: str | date | None,
    projects: Iterable[str] | None = None,
) -> pd.DataFrame:
    month = _period_start(period)
    project_where, project_params = _project_clause(projects)
    sql = f"""
        SELECT *
        FROM analytics.v_stock_movimiento_mensual_export
        WHERE periodo_mes = %s
        {project_where}
        ORDER BY proyecto
    """
    summary = _query_df(sql, [month, *project_params])
    if summary.empty:
        return summary
    return _attach_optional_coverage(summary)


def fetch_month_movements(
    period: str | date | None,
    projects: Iterable[str] | None = None,
) -> pd.DataFrame:
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
    return (
        '"S/ "#,##0.00'
        if str(currency).upper() in {"PEN", "SOLES", "S/"}
        else '"US$ "#,##0.00'
    )


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


def _write_summary_sheet(
    writer: pd.ExcelWriter,
    summary: pd.DataFrame,
    period: date,
    generated_at: datetime,
) -> None:
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
    worksheet.set_column("B:E", 22)
    worksheet.set_column("F:G", 30)
    worksheet.set_row(start_row, 38)
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
        9,
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
        "SEPARACION": workbook.add_format({
            "border": 1,
            "border_color": "#E0E5E8",
            "bg_color": "#FCE4D6",
            "align": "center",
        }),
        "CAIDA": workbook.add_format({
            "border": 1,
            "border_color": "#E0E5E8",
            "bg_color": "#F4CCCC",
            "align": "center",
        }),
        "VENTA": workbook.add_format({
            "border": 1,
            "border_color": "#E0E5E8",
            "bg_color": "#D9EAD3",
            "align": "center",
        }),
    }

    currency = (
        movements["moneda"].mode().iat[0]
        if not movements.empty and not movements["moneda"].mode().empty
        else "PEN"
    )
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
            worksheet.write_datetime(
                r,
                1,
                pd.Timestamp(fecha_evento).to_pydatetime(),
                date_fmt,
            )
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


def _write_control_sheet(
    writer: pd.ExcelWriter,
    summary: pd.DataFrame,
    period: date,
    generated_at: datetime,
) -> None:
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

        coverage = row.get("cobertura_stock_disponible_ratio")
        if pd.isna(coverage):
            worksheet.write_blank(r, 3, None, pct_fmt)
        else:
            worksheet.write(r, 3, coverage, pct_fmt)

        gap = row.get("gap_stock_disponible")
        if pd.isna(gap):
            worksheet.write_blank(r, 4, None, body_fmt)
        else:
            worksheet.write(r, 4, gap, body_fmt)

        worksheet.write(r, 5, row.get("calidad_stock_historico", ""), body_fmt)
        worksheet.write(r, 6, row.get("metodo_stock_historico", ""), body_fmt)
        worksheet.write(r, 7, row.get("metodo_movimiento", ""), body_fmt)

    note_row = start_row + len(summary) + 3
    worksheet.write(note_row, 0, "Contrato", header_fmt)
    worksheet.merge_range(
        note_row,
        1,
        note_row,
        7,
        "Absorción principal = departamentos. Movimiento neto = separaciones efectivas - caídas efectivas. "
        "Ventas/minutas se muestran aparte. El stock histórico se deriva del ledger observado; si no existe "
        "snapshot certificado actual, la cobertura se deja vacía y se declara explícitamente en CALIDAD.",
        body_fmt,
    )

    worksheet.set_column("A:A", 24)
    worksheet.set_column("B:C", 22)
    worksheet.set_column("D:E", 20)
    worksheet.set_column("F:H", 38)
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
