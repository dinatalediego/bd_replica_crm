from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQL_PATH = ROOT / "sql" / "50_stock_export" / "00_stock_export.sql"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "stock_disponible"


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


def install_stock_export_sql(sql_path: Path = DEFAULT_SQL_PATH) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def _fetch_dataframe(projects: Iterable[str] | None = None) -> pd.DataFrame:
    where = ""
    params: list[str] = []
    if projects:
        normalized = [p.strip() for p in projects if p and p.strip()]
        if normalized:
            placeholders = ", ".join(["%s"] * len(normalized))
            where = f" AND proyecto IN ({placeholders})"
            params.extend(normalized)

    sql = f"""
        SELECT
            proyecto,
            tipo_unidad,
            unidad,
            nombre_tipologia,
            piso,
            area_total,
            precio_lista,
            discount_pct,
            precio_con_descuento,
            moneda,
            fecha_actualizacion_dato,
            esquema_fuente,
            unidad_fuente_key
        FROM analytics.v_stock_disponible_export
        WHERE tipo_unidad IN ('Departamento', 'Estacionamiento', 'Depósito')
        {where}
        ORDER BY proyecto, tipo_unidad, unidad
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            columns = [d.name for d in cur.description]
    return pd.DataFrame(rows, columns=columns)


def _safe_sheet_name(name: str) -> str:
    forbidden = "[]:*?/\\"
    clean = "".join("_" if c in forbidden else c for c in name)
    return clean[:31] or "Proyecto"


def _money_format(currency: str) -> str:
    return 'S/ #,##0.00' if str(currency).upper() in {"PEN", "SOLES", "S/"} else '$ #,##0.00'


def _write_project_sheet(writer: pd.ExcelWriter, project: str, df: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    sheet_name = _safe_sheet_name(project.upper())
    worksheet = workbook.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = worksheet

    title_fmt = workbook.add_format({
        "bold": True, "font_size": 16, "font_color": "#FFFFFF",
        "bg_color": "#1F4E3D", "align": "left", "valign": "vcenter"
    })
    subtitle_fmt = workbook.add_format({
        "font_size": 10, "font_color": "#4F4F4F", "italic": True
    })
    header_fmt = workbook.add_format({
        "bold": True, "font_color": "#1F1F1F", "bg_color": "#C6E0B4",
        "border": 1, "border_color": "#A6A6A6", "align": "center", "valign": "vcenter"
    })
    text_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6"})
    center_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6", "align": "center"})
    pct_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6", "num_format": "0%", "align": "center"})
    money_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6", "num_format": _money_format(df["moneda"].mode().iat[0] if not df.empty else "PEN")})
    date_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6", "num_format": "dd/mm/yyyy", "align": "center"})

    worksheet.merge_range("A1:H1", f"STOCK DISPONIBLE · {project}", title_fmt)
    worksheet.write("A2", f"Actualizado al {generated_at.strftime('%d/%m/%Y – %H:%M')}", subtitle_fmt)
    worksheet.write("A3", "Incluye departamentos, estacionamientos y depósitos. Fuente: Medallio DW.", subtitle_fmt)

    export_cols = [
        ("tipo_unidad", "TIPO"),
        ("unidad", "UNIDAD"),
        ("nombre_tipologia", "TIPOLOGÍA"),
        ("piso", "PISO"),
        ("area_total", "ÁREA M²"),
        ("precio_lista", "PRECIO LISTA"),
        ("discount_pct", "DSCTO."),
        ("precio_con_descuento", "PRECIO CON DESCUENTO"),
    ]

    start_row = 4
    for col_idx, (_, label) in enumerate(export_cols):
        worksheet.write(start_row, col_idx, label, header_fmt)

    for row_idx, (_, row) in enumerate(df.iterrows(), start=start_row + 1):
        for col_idx, (field, _) in enumerate(export_cols):
            value = row[field]
            if pd.isna(value):
                value = ""
            if field in {"tipo_unidad", "unidad", "nombre_tipologia"}:
                fmt = text_fmt
            elif field == "piso":
                fmt = center_fmt
            elif field == "discount_pct":
                fmt = pct_fmt
            elif field in {"precio_lista", "precio_con_descuento"}:
                fmt = money_fmt
            else:
                fmt = center_fmt
            worksheet.write(row_idx, col_idx, value, fmt)

    last_row = start_row + max(len(df), 1)
    worksheet.autofilter(start_row, 0, last_row, len(export_cols) - 1)
    worksheet.freeze_panes(start_row + 1, 2)
    worksheet.set_row(0, 28)
    worksheet.set_column("A:A", 18)
    worksheet.set_column("B:B", 15)
    worksheet.set_column("C:C", 18)
    worksheet.set_column("D:D", 10)
    worksheet.set_column("E:E", 12)
    worksheet.set_column("F:F", 18)
    worksheet.set_column("G:G", 11)
    worksheet.set_column("H:H", 22)
    worksheet.hide_gridlines(2)


def _write_summary_sheet(writer: pd.ExcelWriter, df: pd.DataFrame, generated_at: datetime) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet("00_RESUMEN")
    writer.sheets["00_RESUMEN"] = worksheet

    title_fmt = workbook.add_format({
        "bold": True, "font_size": 17, "font_color": "#FFFFFF",
        "bg_color": "#1F4E3D", "align": "left", "valign": "vcenter"
    })
    subtitle_fmt = workbook.add_format({"font_size": 10, "font_color": "#4F4F4F", "italic": True})
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#C6E0B4", "border": 1,
        "border_color": "#A6A6A6", "align": "center", "valign": "vcenter"
    })
    body_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6"})
    int_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6", "num_format": "0", "align": "center"})
    money_fmt = workbook.add_format({"border": 1, "border_color": "#E7E6E6", "num_format": "S/ #,##0.00"})

    worksheet.merge_range("A1:G1", "STOCK DISPONIBLE · RESUMEN EJECUTIVO", title_fmt)
    worksheet.write("A2", f"Actualizado al {generated_at.strftime('%d/%m/%Y – %H:%M')}", subtitle_fmt)
    worksheet.write("A3", "Fuente única: analytics.v_stock_disponible_export · Medallio DW", subtitle_fmt)

    summary = (
        df.assign(
            depa=(df["tipo_unidad"] == "Departamento").astype(int),
            estac=(df["tipo_unidad"] == "Estacionamiento").astype(int),
            depo=(df["tipo_unidad"] == "Depósito").astype(int),
        )
        .groupby("proyecto", as_index=False)
        .agg(
            departamentos=("depa", "sum"),
            estacionamientos=("estac", "sum"),
            depositos=("depo", "sum"),
            stock_total=("unidad", "count"),
            valor_lista=("precio_lista", "sum"),
            valor_descuento=("precio_con_descuento", "sum"),
        )
        if not df.empty else pd.DataFrame(columns=["proyecto", "departamentos", "estacionamientos", "depositos", "stock_total", "valor_lista", "valor_descuento"])
    )

    headers = ["PROYECTO", "DPTOS.", "ESTAC.", "DEPÓSITOS", "STOCK TOTAL", "VALOR LISTA", "VALOR CON DSCTO."]
    for c, h in enumerate(headers):
        worksheet.write(4, c, h, header_fmt)

    for r, (_, row) in enumerate(summary.iterrows(), start=5):
        worksheet.write(r, 0, row["proyecto"], body_fmt)
        worksheet.write(r, 1, int(row["departamentos"]), int_fmt)
        worksheet.write(r, 2, int(row["estacionamientos"]), int_fmt)
        worksheet.write(r, 3, int(row["depositos"]), int_fmt)
        worksheet.write(r, 4, int(row["stock_total"]), int_fmt)
        worksheet.write(r, 5, row["valor_lista"], money_fmt)
        worksheet.write(r, 6, row["valor_descuento"], money_fmt)

    worksheet.freeze_panes(5, 1)
    worksheet.set_row(0, 30)
    worksheet.set_column("A:A", 22)
    worksheet.set_column("B:E", 13)
    worksheet.set_column("F:G", 21)
    worksheet.hide_gridlines(2)


def export_stock_excel(
    projects: Iterable[str] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    df = _fetch_dataframe(projects)
    generated_at = datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"Stock_Disponible_{generated_at:%Y_%m_%d}.xlsx"

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        _write_summary_sheet(writer, df, generated_at)
        for project, project_df in df.groupby("proyecto", sort=True):
            _write_project_sheet(writer, str(project), project_df.reset_index(drop=True), generated_at)

    return output_path
