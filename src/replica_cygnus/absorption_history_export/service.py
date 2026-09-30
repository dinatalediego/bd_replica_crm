from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from replica_cygnus.monthly_stock_export.service import (
    MONTH_NAMES_ES,
    _query_df,
    install_monthly_stock_sql,
    validate_monthly_stock_dependencies,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "output" / "absorcion_historica"
DEFAULT_PROJECTS = ["Fénix", "Urbanzen", "Tizón y Bueno"]

MONTHLY_METRIC_COLUMNS = [
    "stock_inicio_observado",
    "altas_mes",
    "separaciones_brutas_mes",
    "caidas_mes",
    "movimiento_neto_mes",
    "ventas_minutas_mes",
    "saldo_final_observado",
    "absorcion_bruta_mes",
    "absorcion_neta_mes",
    "absorcion_neta_6m",
]


def _project_filter(projects: Iterable[str] | None) -> tuple[str, list[object]]:
    if not projects:
        return "", []
    clean = [str(p).strip() for p in projects if str(p).strip()]
    if not clean:
        return "", []
    placeholders = ", ".join(["%s"] * len(clean))
    return f" AND m.proyecto IN ({placeholders})", clean


def _fetch_history_raw(projects: Iterable[str] | None = None) -> pd.DataFrame:
    where, params = _project_filter(projects)
    sql = f"""
        SELECT
            m.*,
            p.fecha_inicio_venta AS fecha_inicio_comercial
        FROM analytics.v_stock_movimiento_mensual_export m
        LEFT JOIN core.dim_proyecto p
          ON p.codigo_proyecto = m.codigo_proyecto
        WHERE 1=1
        {where}
        ORDER BY m.proyecto, m.periodo_mes
    """
    return _query_df(sql, params or None)


def _fetch_movements_raw(projects: Iterable[str] | None = None) -> pd.DataFrame:
    where, params = _project_filter(projects)
    sql = f"""
        SELECT
            m.periodo_mes,
            m.codigo_proyecto,
            m.proyecto,
            m.unidad,
            m.tipo_unidad,
            m.piso,
            m.area_total,
            m.movimiento,
            m.fecha_evento,
            m.codigo_proforma,
            m.estado_actual,
            m.precio_lista,
            m.discount_pct,
            m.precio_con_descuento,
            m.precio_venta_actual,
            m.moneda,
            m.source_table,
            m.source_id,
            m.transition_reason,
            m.event_rank
        FROM analytics.v_stock_movimiento_mensual_unidad_export m
        WHERE 1=1
        {where}
        ORDER BY m.proyecto, m.periodo_mes, m.fecha_evento, m.unidad, m.movimiento
    """
    return _query_df(sql, params or None)


def _month_floor(value: object) -> pd.Timestamp | pd.NaT:
    if value is None or pd.isna(value):
        return pd.NaT
    ts = pd.Timestamp(value)
    return pd.Timestamp(ts.year, ts.month, 1)


def _prepare_project_history(project_df: pd.DataFrame) -> pd.DataFrame:
    if project_df.empty:
        return project_df.copy()

    observed = project_df.copy()
    observed["periodo_mes"] = pd.to_datetime(observed["periodo_mes"])
    observed = observed.sort_values("periodo_mes").reset_index(drop=True)

    first_observed = observed["periodo_mes"].min()
    commercial_values = observed["fecha_inicio_comercial"].dropna()
    commercial_start = _month_floor(commercial_values.iloc[0]) if not commercial_values.empty else pd.NaT

    # Never discard observed evidence. If the commercial-start master data is
    # later than an observed event, start at the earliest evidence and flag it.
    if pd.isna(commercial_start):
        timeline_start = first_observed
    else:
        timeline_start = min(first_observed, commercial_start)

    active_mask = (
        observed["stock_inicio_observado"].fillna(0).astype(float).gt(0)
        | observed["saldo_final_observado"].fillna(0).astype(float).gt(0)
        | observed["altas_mes"].fillna(0).astype(float).gt(0)
    )
    if active_mask.any():
        last_stock_month = observed.loc[active_mask, "periodo_mes"].max()
    else:
        last_stock_month = observed["periodo_mes"].max()

    timeline = pd.DataFrame({
        "periodo_mes": pd.date_range(timeline_start, last_stock_month, freq="MS")
    })
    out = timeline.merge(observed, on="periodo_mes", how="left", suffixes=("", "_src"))

    # Static identifiers should remain visible even before first ledger evidence.
    for col in ["codigo_proyecto", "proyecto", "tipo_unidad_consolidado", "fecha_inicio_comercial"]:
        if col in out.columns:
            values = observed[col].dropna()
            if not values.empty:
                out[col] = out[col].fillna(values.iloc[0])

    out["evidencia_mes"] = out["primera_fecha_observada"].notna().map(
        {True: "OBSERVADO_LEDGER", False: "SIN_EVIDENCIA_LEDGER"}
    )

    # Event counts are legitimately zero for observed months. Pre-ledger months
    # remain blank to avoid fabricating historical measurements.
    observed_mask = out["evidencia_mes"].eq("OBSERVADO_LEDGER")
    count_cols = [
        "altas_mes",
        "separaciones_brutas_mes",
        "caidas_mes",
        "movimiento_neto_mes",
        "ventas_minutas_mes",
    ]
    for col in count_cols:
        if col in out.columns:
            out.loc[observed_mask, col] = out.loc[observed_mask, col].fillna(0)

    out["periodo"] = out["periodo_mes"].map(
        lambda x: f"{MONTH_NAMES_ES[int(x.month)].title()} {int(x.year)}"
    )
    out["mes_n_desde_inicio"] = range(1, len(out) + 1)

    # Cumulative contract over observed ledger stock.
    for col in [
        "stock_ofertado_acumulado",
        "separaciones_brutas_acumuladas",
        "caidas_acumuladas",
        "movimiento_neto_acumulado",
        "ventas_minutas_acumuladas",
        "absorcion_stock_acumulada",
        "absorcion_neta_eventos_acumulada",
    ]:
        out[col] = pd.NA

    observed_idx = out.index[observed_mask].tolist()
    if observed_idx:
        obs = out.loc[observed_idx].copy()
        base_stock = pd.to_numeric(obs["stock_inicio_observado"], errors="coerce").iloc[0]
        base_stock = 0.0 if pd.isna(base_stock) else float(base_stock)
        altas = pd.to_numeric(obs["altas_mes"], errors="coerce").fillna(0.0)
        sep = pd.to_numeric(obs["separaciones_brutas_mes"], errors="coerce").fillna(0.0)
        caidas = pd.to_numeric(obs["caidas_mes"], errors="coerce").fillna(0.0)
        neto = pd.to_numeric(obs["movimiento_neto_mes"], errors="coerce").fillna(0.0)
        ventas = pd.to_numeric(obs["ventas_minutas_mes"], errors="coerce").fillna(0.0)
        saldo = pd.to_numeric(obs["saldo_final_observado"], errors="coerce")

        stock_total = base_stock + altas.cumsum()
        sep_acum = sep.cumsum()
        caidas_acum = caidas.cumsum()
        neto_acum = neto.cumsum()
        ventas_acum = ventas.cumsum()

        out.loc[observed_idx, "stock_ofertado_acumulado"] = stock_total.values
        out.loc[observed_idx, "separaciones_brutas_acumuladas"] = sep_acum.values
        out.loc[observed_idx, "caidas_acumuladas"] = caidas_acum.values
        out.loc[observed_idx, "movimiento_neto_acumulado"] = neto_acum.values
        out.loc[observed_idx, "ventas_minutas_acumuladas"] = ventas_acum.values
        out.loc[observed_idx, "absorcion_stock_acumulada"] = (
            (stock_total - saldo) / stock_total.replace(0, pd.NA)
        ).values
        out.loc[observed_idx, "absorcion_neta_eventos_acumulada"] = (
            neto_acum / stock_total.replace(0, pd.NA)
        ).values

    start_before_evidence = (
        not pd.isna(commercial_start) and commercial_start < first_observed
    )
    event_before_start = (
        not pd.isna(commercial_start) and first_observed < commercial_start
    )
    out["calidad_inicio"] = "OK"
    if start_before_evidence:
        out["calidad_inicio"] = "INICIO_COMERCIAL_ANTES_DE_PRIMERA_EVIDENCIA"
    elif event_before_start:
        out["calidad_inicio"] = "EVENTO_ANTES_DE_INICIO_COMERCIAL_DECLARADO"

    return out


def fetch_absorption_history(projects: Iterable[str] | None = None) -> pd.DataFrame:
    validate_monthly_stock_dependencies()
    install_monthly_stock_sql()
    raw = _fetch_history_raw(projects)
    if raw.empty:
        return raw
    frames = []
    for _, group in raw.groupby("proyecto", sort=True):
        frames.append(_prepare_project_history(group))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _safe_sheet_name(name: str) -> str:
    forbidden = "[]:*?/\\"
    clean = "".join("_" if c in forbidden else c for c in str(name))
    return clean[:31] or "Hoja"


def _safe_filename(name: str) -> str:
    forbidden = '<>:"/\\|?*'
    clean = "".join("_" if c in forbidden else c for c in str(name))
    return "_".join(clean.split())


def _money_format(currency: str) -> str:
    return '"S/ "#,##0.00' if str(currency).upper() in {"PEN", "SOLES", "S/"} else '"US$ "#,##0.00'


def _excel_value(value: object) -> object:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def _formats(workbook):
    return {
        "title": workbook.add_format({
            "bold": True, "font_size": 17, "font_color": "#FFFFFF",
            "bg_color": "#1F5E43", "align": "left", "valign": "vcenter",
            "top": 2, "top_color": "#2ECC71",
        }),
        "subtitle": workbook.add_format({
            "font_size": 10, "font_color": "#4F4F4F", "italic": True,
        }),
        "header": workbook.add_format({
            "bold": True, "font_color": "#1B2230", "bg_color": "#C6E0B4",
            "border": 1, "border_color": "#55B878", "align": "center",
            "valign": "vcenter", "text_wrap": True,
        }),
        "text": workbook.add_format({"border": 1, "border_color": "#E0E5E8"}),
        "center": workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "align": "center",
        }),
        "int": workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "align": "center", "num_format": "0",
        }),
        "pct": workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "align": "center", "num_format": "0.0%",
        }),
        "date": workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "align": "center", "num_format": "dd/mm/yyyy",
        }),
        "kpi_label": workbook.add_format({
            "bold": True, "font_color": "#50606D", "font_size": 9,
            "bg_color": "#F4F7F5", "border": 1, "border_color": "#D9E2DC", "align": "center",
        }),
        "kpi_value": workbook.add_format({
            "bold": True, "font_size": 15, "font_color": "#0A2F43",
            "bg_color": "#FFFFFF", "border": 1, "border_color": "#D9E2DC", "align": "center",
        }),
        "kpi_pct": workbook.add_format({
            "bold": True, "font_size": 15, "font_color": "#0A2F43",
            "bg_color": "#FFFFFF", "border": 1, "border_color": "#D9E2DC",
            "align": "center", "num_format": "0.0%",
        }),
        "note": workbook.add_format({
            "font_color": "#6B7280", "italic": True, "text_wrap": True,
        }),
    }


def _write_title(worksheet, fmt, end_col: int, title: str, generated_at: datetime) -> None:
    worksheet.merge_range(0, 0, 0, end_col, title, fmt["title"])
    worksheet.write(1, 0, f"Actualizado al {generated_at:%d/%m/%Y}", fmt["subtitle"])
    worksheet.set_row(0, 30)


def _history_columns() -> list[tuple[str, str, str]]:
    return [
        ("periodo", "PERIODO", "text"),
        ("stock_inicio_observado", "STOCK INICIO", "int"),
        ("altas_mes", "ALTAS", "int"),
        ("separaciones_brutas_mes", "SEPARACIONES", "int"),
        ("caidas_mes", "CAÍDAS", "int"),
        ("movimiento_neto_mes", "MOV. NETO", "int"),
        ("ventas_minutas_mes", "VENDIDAS / MINUTAS", "int"),
        ("saldo_final_observado", "SALDO FINAL", "int"),
        ("absorcion_bruta_mes", "ABS. BRUTA % MES", "pct"),
        ("absorcion_neta_mes", "ABS. NETA % MES", "pct"),
        ("absorcion_neta_6m", "ABS. NETA % 6M", "pct"),
        ("stock_ofertado_acumulado", "STOCK OFERTADO ACUM.", "int"),
        ("movimiento_neto_acumulado", "MOV. NETO ACUM.", "int"),
        ("ventas_minutas_acumuladas", "VENDIDAS / MINUTAS ACUM.", "int"),
        ("absorcion_stock_acumulada", "ABS. STOCK ACUM. %", "pct"),
        ("absorcion_neta_eventos_acumulada", "ABS. NETA EVENTOS ACUM. %", "pct"),
        ("evidencia_mes", "EVIDENCIA", "text"),
    ]


def _write_history_table(worksheet, workbook, fmt, history: pd.DataFrame, start_row: int = 7) -> int:
    cols = _history_columns()
    for c, (_, label, _) in enumerate(cols):
        worksheet.write(start_row, c, label, fmt["header"])

    for r, (_, row) in enumerate(history.iterrows(), start=start_row + 1):
        for c, (field, _, kind) in enumerate(cols):
            value = _excel_value(row.get(field))
            worksheet.write(r, c, value, fmt[kind])

    last_row = start_row + max(len(history), 1)
    worksheet.autofilter(start_row, 0, last_row, len(cols) - 1)
    worksheet.freeze_panes(start_row + 1, 1)
    worksheet.set_row(start_row, 36)
    worksheet.set_column(0, 0, 18)
    worksheet.set_column(1, 7, 15)
    worksheet.set_column(8, 10, 17)
    worksheet.set_column(11, 15, 22)
    worksheet.set_column(16, 16, 26)
    worksheet.hide_gridlines(2)
    return last_row


def _add_absorption_chart(worksheet, workbook, history: pd.DataFrame, table_start_row: int, chart_cell: str) -> None:
    if history.empty:
        return
    # Columns: A period, J monthly net absorption, O accumulated stock absorption.
    first_excel_row = table_start_row + 2
    last_excel_row = table_start_row + 1 + len(history)
    chart = workbook.add_chart({"type": "line"})
    sheet = worksheet.get_name().replace("'", "''")
    chart.add_series({
        "name": "Absorción neta mensual",
        "categories": f"='{sheet}'!$A${first_excel_row}:$A${last_excel_row}",
        "values": f"='{sheet}'!$J${first_excel_row}:$J${last_excel_row}",
        "marker": {"type": "circle", "size": 4},
    })
    chart.add_series({
        "name": "Absorción stock acumulada",
        "categories": f"='{sheet}'!$A${first_excel_row}:$A${last_excel_row}",
        "values": f"='{sheet}'!$O${first_excel_row}:$O${last_excel_row}",
        "marker": {"type": "circle", "size": 4},
    })
    chart.set_title({"name": "Absorción mensual vs acumulada"})
    chart.set_y_axis({"num_format": "0%"})
    chart.set_legend({"position": "bottom"})
    chart.set_size({"width": 720, "height": 320})
    worksheet.insert_chart(chart_cell, chart)


def _project_metadata(history: pd.DataFrame) -> dict[str, object]:
    observed = history[history["evidencia_mes"] == "OBSERVADO_LEDGER"]
    commercial = history["fecha_inicio_comercial"].dropna()
    return {
        "inicio_comercial": commercial.iloc[0] if not commercial.empty else pd.NaT,
        "primer_mes_observado": observed["periodo_mes"].min() if not observed.empty else pd.NaT,
        "ultimo_mes_stock": history["periodo_mes"].max() if not history.empty else pd.NaT,
        "calidad_inicio": history["calidad_inicio"].iloc[0] if not history.empty else "SIN_DATOS",
    }


def _write_project_accumulated_sheet(writer, project: str, history: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet("ACUMULADO")
    writer.sheets["ACUMULADO"] = worksheet
    fmt = _formats(workbook)
    _write_title(worksheet, fmt, 16, f"ABSORCIÓN HISTÓRICA · {project}", generated_at)

    meta = _project_metadata(history)
    worksheet.write(3, 0, "Inicio comercial", fmt["kpi_label"])
    worksheet.write(3, 2, "Primer mes observado", fmt["kpi_label"])
    worksheet.write(3, 4, "Último mes con stock", fmt["kpi_label"])
    worksheet.write(4, 0, _excel_value(meta["inicio_comercial"]), fmt["date"])
    worksheet.write(4, 2, _excel_value(meta["primer_mes_observado"]), fmt["date"])
    worksheet.write(4, 4, _excel_value(meta["ultimo_mes_stock"]), fmt["date"])
    worksheet.write(3, 6, "Calidad inicio", fmt["kpi_label"])
    worksheet.merge_range(4, 6, 4, 9, meta["calidad_inicio"], fmt["kpi_value"])

    start_row = 7
    _write_history_table(worksheet, workbook, fmt, history, start_row=start_row)
    _add_absorption_chart(worksheet, workbook, history, start_row, "S8")


def _movement_formats(workbook, fmt):
    return {
        "SEPARACION": workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "bg_color": "#FCE4D6", "align": "center"
        }),
        "CAIDA": workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "bg_color": "#F4CCCC", "align": "center"
        }),
        "VENTA": workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "bg_color": "#D9EAD3", "align": "center"
        }),
        "DEFAULT": fmt["center"],
    }


def _write_month_sheet(writer, project: str, month_row: pd.Series, movements: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    fmt = _formats(workbook)
    month = pd.Timestamp(month_row["periodo_mes"])
    sheet_name = _safe_sheet_name(f"{month:%Y-%m}")
    worksheet = workbook.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = worksheet

    title = f"ABSORCIÓN Y MOVIMIENTO · {project} · {MONTH_NAMES_ES[month.month]} {month.year}"
    _write_title(worksheet, fmt, 11, title, generated_at)

    kpis = [
        ("STOCK INICIO", month_row.get("stock_inicio_observado"), "kpi_value"),
        ("ALTAS", month_row.get("altas_mes"), "kpi_value"),
        ("SEPARACIONES", month_row.get("separaciones_brutas_mes"), "kpi_value"),
        ("CAÍDAS", month_row.get("caidas_mes"), "kpi_value"),
        ("MOV. NETO", month_row.get("movimiento_neto_mes"), "kpi_value"),
        ("VENDIDAS/MINUTAS", month_row.get("ventas_minutas_mes"), "kpi_value"),
        ("SALDO FINAL", month_row.get("saldo_final_observado"), "kpi_value"),
        ("ABS. NETA MES", month_row.get("absorcion_neta_mes"), "kpi_pct"),
        ("ABS. STOCK ACUM.", month_row.get("absorcion_stock_acumulada"), "kpi_pct"),
    ]
    for idx, (label, value, value_fmt) in enumerate(kpis):
        c = idx
        worksheet.write(3, c, label, fmt["kpi_label"])
        worksheet.write(4, c, _excel_value(value), fmt[value_fmt])

    worksheet.write(6, 0, "Evidencia", fmt["kpi_label"])
    worksheet.merge_range(6, 1, 6, 4, month_row.get("evidencia_mes", ""), fmt["text"])

    headers = [
        "MOVIMIENTO", "FECHA", "UNIDAD", "ESTADO ACTUAL", "PISO", "ÁREA M²",
        "PRECIO LISTA", "DSCTO.", "PRECIO CON DESCUENTO", "PRECIO VENTA ACTUAL",
        "CÓDIGO PROFORMA", "FUENTE",
    ]
    start_row = 8
    for c, header in enumerate(headers):
        worksheet.write(start_row, c, header, fmt["header"])

    if movements.empty:
        worksheet.merge_range(start_row + 1, 0, start_row + 2, 11,
                              "Sin movimientos efectivos observados para este mes.", fmt["note"])
    else:
        movement_fmt = _movement_formats(workbook, fmt)
        currency = movements["moneda"].mode().iat[0] if not movements["moneda"].mode().empty else "PEN"
        money_fmt = workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "num_format": _money_format(currency)
        })
        for r, (_, row) in enumerate(movements.iterrows(), start=start_row + 1):
            move = str(row.get("movimiento", ""))
            worksheet.write(r, 0, move, movement_fmt.get(move, movement_fmt["DEFAULT"]))
            worksheet.write(r, 1, _excel_value(row.get("fecha_evento")), fmt["date"])
            worksheet.write(r, 2, _excel_value(row.get("unidad")), fmt["text"])
            worksheet.write(r, 3, _excel_value(row.get("estado_actual")), fmt["text"])
            worksheet.write(r, 4, _excel_value(row.get("piso")), fmt["center"])
            worksheet.write(r, 5, _excel_value(row.get("area_total")), fmt["center"])
            worksheet.write(r, 6, _excel_value(row.get("precio_lista")), money_fmt)
            worksheet.write(r, 7, _excel_value(row.get("discount_pct")), fmt["pct"])
            worksheet.write(r, 8, _excel_value(row.get("precio_con_descuento")), money_fmt)
            worksheet.write(r, 9, _excel_value(row.get("precio_venta_actual")), money_fmt)
            worksheet.write(r, 10, _excel_value(row.get("codigo_proforma")), fmt["text"])
            worksheet.write(r, 11, _excel_value(row.get("source_table")), fmt["text"])

    worksheet.freeze_panes(start_row + 1, 3)
    worksheet.set_column("A:A", 15)
    worksheet.set_column("B:B", 13)
    worksheet.set_column("C:D", 18)
    worksheet.set_column("E:E", 9)
    worksheet.set_column("F:F", 12)
    worksheet.set_column("G:J", 20)
    worksheet.set_column("K:L", 22)
    worksheet.hide_gridlines(2)


def _write_project_control(writer, project: str, history: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet("CONTROL")
    writer.sheets["CONTROL"] = worksheet
    fmt = _formats(workbook)
    _write_title(worksheet, fmt, 6, f"CONTROL DE EVIDENCIA · {project}", generated_at)

    meta = _project_metadata(history)
    rows = [
        ("Proyecto", project),
        ("Inicio comercial declarado", meta["inicio_comercial"]),
        ("Primer mes observado por ledger", meta["primer_mes_observado"]),
        ("Último mes incluido por stock observado", meta["ultimo_mes_stock"]),
        ("Calidad de inicio", meta["calidad_inicio"]),
        ("Scope", "DEPARTAMENTO"),
        ("Absorción mensual", "movimiento_neto_mes / stock_inicio_observado"),
        ("Absorción stock acumulada", "(stock_ofertado_acumulado - saldo_final) / stock_ofertado_acumulado"),
        ("Absorción neta eventos acumulada", "movimiento_neto_acumulado / stock_ofertado_acumulado"),
        ("Histórico", "OBSERVADO_LEDGER; no se fabrican meses anteriores sin evidencia"),
    ]
    worksheet.write(4, 0, "CAMPO", fmt["header"])
    worksheet.write(4, 1, "VALOR", fmt["header"])
    for r, (key, value) in enumerate(rows, start=5):
        worksheet.write(r, 0, key, fmt["text"])
        if isinstance(value, (pd.Timestamp, datetime, date)) and not pd.isna(value):
            worksheet.write(r, 1, _excel_value(value), fmt["date"])
        else:
            worksheet.write(r, 1, _excel_value(value), fmt["text"])
    worksheet.set_column("A:A", 34)
    worksheet.set_column("B:B", 70)
    worksheet.hide_gridlines(2)


def export_project_histories(
    projects: Iterable[str] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR / "por_proyecto",
) -> list[Path]:
    selected = list(projects) if projects is not None else DEFAULT_PROJECTS
    history = fetch_absorption_history(selected)
    if history.empty:
        raise RuntimeError("No hay historia de absorción para los proyectos seleccionados.")
    movements = _fetch_movements_raw(selected)
    if not movements.empty:
        movements["periodo_mes"] = pd.to_datetime(movements["periodo_mes"])

    generated_at = datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    for project, project_history in history.groupby("proyecto", sort=True):
        project_history = project_history.sort_values("periodo_mes").reset_index(drop=True)
        project_moves = movements[movements["proyecto"] == project].copy() if not movements.empty else pd.DataFrame()
        output = output_dir / f"Absorcion_Historica_{_safe_filename(project)}_{generated_at:%Y_%m_%d}.xlsx"
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            _write_project_accumulated_sheet(writer, str(project), project_history, generated_at)
            for _, month_row in project_history.iterrows():
                month = pd.Timestamp(month_row["periodo_mes"])
                month_moves = (
                    project_moves[project_moves["periodo_mes"] == month].copy()
                    if not project_moves.empty else pd.DataFrame()
                )
                _write_month_sheet(writer, str(project), month_row, month_moves, generated_at)
            _write_project_control(writer, str(project), project_history, generated_at)
        outputs.append(output)
    return outputs


def _write_multi_accumulated_sheet(writer, history: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet("ACUMULADO")
    writer.sheets["ACUMULADO"] = worksheet
    fmt = _formats(workbook)
    projects = sorted(history["proyecto"].dropna().astype(str).unique())
    _write_title(worksheet, fmt, max(8, len(projects) + 2), "ABSORCIÓN HISTÓRICA · MULTIPROYECTO", generated_at)

    latest = (
        history.sort_values("periodo_mes")
        .groupby("proyecto", as_index=False)
        .tail(1)
        .sort_values("proyecto")
    )
    latest_headers = ["PROYECTO", "ÚLTIMO MES", "SALDO FINAL", "ABS. NETA MES", "ABS. STOCK ACUM.", "VENDIDAS/MINUTAS ACUM."]
    for c, h in enumerate(latest_headers):
        worksheet.write(4, c, h, fmt["header"])
    for r, (_, row) in enumerate(latest.iterrows(), start=5):
        worksheet.write(r, 0, row["proyecto"], fmt["text"])
        worksheet.write(r, 1, row["periodo"], fmt["text"])
        worksheet.write(r, 2, _excel_value(row["saldo_final_observado"]), fmt["int"])
        worksheet.write(r, 3, _excel_value(row["absorcion_neta_mes"]), fmt["pct"])
        worksheet.write(r, 4, _excel_value(row["absorcion_stock_acumulada"]), fmt["pct"])
        worksheet.write(r, 5, _excel_value(row["ventas_minutas_acumuladas"]), fmt["int"])

    start_matrix = 5 + len(latest) + 3
    periods = sorted(history["periodo_mes"].dropna().unique())

    # Matrix 1: net monthly absorption by project.
    worksheet.write(start_matrix, 0, "MATRIZ · ABSORCIÓN NETA MENSUAL", fmt["title"])
    worksheet.write(start_matrix + 1, 0, "PERIODO", fmt["header"])
    for c, project in enumerate(projects, start=1):
        worksheet.write(start_matrix + 1, c, project, fmt["header"])
    monthly_pivot = history.pivot_table(index="periodo_mes", columns="proyecto", values="absorcion_neta_mes", aggfunc="first")
    for r, period in enumerate(periods, start=start_matrix + 2):
        ts = pd.Timestamp(period)
        worksheet.write(r, 0, f"{MONTH_NAMES_ES[ts.month].title()} {ts.year}", fmt["text"])
        for c, project in enumerate(projects, start=1):
            val = monthly_pivot.loc[period, project] if period in monthly_pivot.index and project in monthly_pivot.columns else pd.NA
            worksheet.write(r, c, _excel_value(val), fmt["pct"])

    start_matrix2 = start_matrix + 3 + len(periods)
    worksheet.write(start_matrix2, 0, "MATRIZ · ABSORCIÓN STOCK ACUMULADA", fmt["title"])
    worksheet.write(start_matrix2 + 1, 0, "PERIODO", fmt["header"])
    for c, project in enumerate(projects, start=1):
        worksheet.write(start_matrix2 + 1, c, project, fmt["header"])
    accum_pivot = history.pivot_table(index="periodo_mes", columns="proyecto", values="absorcion_stock_acumulada", aggfunc="first")
    for r, period in enumerate(periods, start=start_matrix2 + 2):
        ts = pd.Timestamp(period)
        worksheet.write(r, 0, f"{MONTH_NAMES_ES[ts.month].title()} {ts.year}", fmt["text"])
        for c, project in enumerate(projects, start=1):
            val = accum_pivot.loc[period, project] if period in accum_pivot.index and project in accum_pivot.columns else pd.NA
            worksheet.write(r, c, _excel_value(val), fmt["pct"])

    worksheet.set_column("A:A", 20)
    worksheet.set_column(1, max(1, len(projects)), 18)
    worksheet.hide_gridlines(2)


def _write_multi_project_sheet(writer, project: str, history: pd.DataFrame, movements: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    sheet_name = _safe_sheet_name(project.upper())
    worksheet = workbook.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = worksheet
    fmt = _formats(workbook)
    _write_title(worksheet, fmt, 16, f"ABSORCIÓN HISTÓRICA · {project}", generated_at)
    last_row = _write_history_table(worksheet, workbook, fmt, history, start_row=4)
    _add_absorption_chart(worksheet, workbook, history, 4, "S5")

    detail_start = last_row + 3
    worksheet.write(detail_start, 0, "MOVIMIENTOS DE UNIDAD · HISTÓRICO", fmt["title"])
    headers = [
        "PERIODO", "MOVIMIENTO", "FECHA", "UNIDAD", "ESTADO ACTUAL", "PISO", "ÁREA M²",
        "PRECIO LISTA", "DSCTO.", "PRECIO CON DESCUENTO", "PRECIO VENTA ACTUAL", "PROFORMA", "FUENTE",
    ]
    for c, h in enumerate(headers):
        worksheet.write(detail_start + 1, c, h, fmt["header"])

    if not movements.empty:
        currency = movements["moneda"].mode().iat[0] if not movements["moneda"].mode().empty else "PEN"
        money_fmt = workbook.add_format({
            "border": 1, "border_color": "#E0E5E8", "num_format": _money_format(currency)
        })
        move_fmt = _movement_formats(workbook, fmt)
        for r, (_, row) in enumerate(movements.iterrows(), start=detail_start + 2):
            month = pd.Timestamp(row["periodo_mes"])
            worksheet.write(r, 0, f"{MONTH_NAMES_ES[month.month].title()} {month.year}", fmt["text"])
            move = str(row.get("movimiento", ""))
            worksheet.write(r, 1, move, move_fmt.get(move, move_fmt["DEFAULT"]))
            worksheet.write(r, 2, _excel_value(row.get("fecha_evento")), fmt["date"])
            worksheet.write(r, 3, _excel_value(row.get("unidad")), fmt["text"])
            worksheet.write(r, 4, _excel_value(row.get("estado_actual")), fmt["text"])
            worksheet.write(r, 5, _excel_value(row.get("piso")), fmt["center"])
            worksheet.write(r, 6, _excel_value(row.get("area_total")), fmt["center"])
            worksheet.write(r, 7, _excel_value(row.get("precio_lista")), money_fmt)
            worksheet.write(r, 8, _excel_value(row.get("discount_pct")), fmt["pct"])
            worksheet.write(r, 9, _excel_value(row.get("precio_con_descuento")), money_fmt)
            worksheet.write(r, 10, _excel_value(row.get("precio_venta_actual")), money_fmt)
            worksheet.write(r, 11, _excel_value(row.get("codigo_proforma")), fmt["text"])
            worksheet.write(r, 12, _excel_value(row.get("source_table")), fmt["text"])

    worksheet.set_column("A:A", 18)
    worksheet.set_column("B:B", 16)
    worksheet.set_column("C:C", 13)
    worksheet.set_column("D:E", 18)
    worksheet.set_column("F:F", 9)
    worksheet.set_column("G:G", 12)
    worksheet.set_column("H:K", 20)
    worksheet.set_column("L:M", 22)


def _write_multi_data_sheet(writer, history: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet("DATA_MENSUAL")
    writer.sheets["DATA_MENSUAL"] = worksheet
    fmt = _formats(workbook)
    _write_title(worksheet, fmt, 18, "DATA MENSUAL CONSOLIDADA", generated_at)
    cols = [("proyecto", "PROYECTO", "text"), *_history_columns()]
    start_row = 4
    for c, (_, label, _) in enumerate(cols):
        worksheet.write(start_row, c, label, fmt["header"])
    for r, (_, row) in enumerate(history.sort_values(["proyecto", "periodo_mes"]).iterrows(), start=start_row + 1):
        for c, (field, _, kind) in enumerate(cols):
            worksheet.write(r, c, _excel_value(row.get(field)), fmt[kind])
    worksheet.autofilter(start_row, 0, start_row + max(len(history), 1), len(cols) - 1)
    worksheet.freeze_panes(start_row + 1, 2)
    worksheet.set_column("A:B", 20)
    worksheet.set_column("C:I", 15)
    worksheet.set_column("J:L", 17)
    worksheet.set_column("M:Q", 22)
    worksheet.set_column("R:R", 26)
    worksheet.hide_gridlines(2)


def export_multi_project_history(
    projects: Iterable[str] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR / "multiproyecto",
) -> Path:
    selected = list(projects) if projects is not None else DEFAULT_PROJECTS
    history = fetch_absorption_history(selected)
    if history.empty:
        raise RuntimeError("No hay historia de absorción para los proyectos seleccionados.")
    movements = _fetch_movements_raw(selected)
    if not movements.empty:
        movements["periodo_mes"] = pd.to_datetime(movements["periodo_mes"])

    generated_at = datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"Absorcion_Historica_Multiproyecto_{generated_at:%Y_%m_%d}.xlsx"

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        _write_multi_accumulated_sheet(writer, history, generated_at)
        for project, project_history in history.groupby("proyecto", sort=True):
            project_history = project_history.sort_values("periodo_mes").reset_index(drop=True)
            project_moves = movements[movements["proyecto"] == project].copy() if not movements.empty else pd.DataFrame()
            _write_multi_project_sheet(writer, str(project), project_history, project_moves, generated_at)
        _write_multi_data_sheet(writer, history, generated_at)

    return output
