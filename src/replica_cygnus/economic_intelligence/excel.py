from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from .data import install_feature_mart, load_monthly_panel


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "output" / "economic_intelligence"


def _sheet_name(value: str) -> str:
    forbidden = "[]:*?/\\"
    return "".join("_" if c in forbidden else c for c in str(value))[:31] or "Proyecto"


def export_absorption_economic_excel(
    projects: Iterable[str] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    """Enhanced absorption workbook.

    Important: `stock_total_departamentos_actual_ref` is a complete CURRENT
    universe reference, not a historical launch-stock reconstruction.
    """
    install_feature_mart()
    panel = load_monthly_panel(projects)
    if panel.empty:
        raise RuntimeError("No hay datos en analytics.v_econ_project_monthly_features.")

    generated = datetime.now()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"Absorcion_Economica_{generated:%Y_%m_%d}.xlsx"

    cols = [
        "periodo_mes",
        "stock_total_departamentos_actual_ref",
        "stock_inicio_observado",
        "altas_mes",
        "altas_acumuladas_ledger",
        "stock_ofertado_observado_acum",
        "cobertura_oferta_ledger_vs_universo_actual",
        "separaciones_brutas_mes",
        "caidas_mes",
        "movimiento_neto_mes",
        "ventas_minutas_mes",
        "saldo_final_observado",
        "absorcion_bruta_mes",
        "absorcion_neta_mes",
        "absorcion_neta_6m",
        "absorcion_stock_acumulada_observada",
        "edad_comercial_meses",
    ]

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        wb = writer.book
        dark = "#1F5E43"
        light = "#C6E0B4"
        header = wb.add_format({"bold": True, "bg_color": light, "font_color": "#17202A", "border": 1, "align": "center", "text_wrap": True})
        title = wb.add_format({"bold": True, "bg_color": dark, "font_color": "#FFFFFF", "font_size": 16, "align": "left"})
        note = wb.add_format({"italic": True, "font_color": "#555555"})
        integer = wb.add_format({"num_format": "0", "align": "center", "border": 1, "border_color": "#E2E8F0"})
        pct = wb.add_format({"num_format": "0.0%", "align": "center", "border": 1, "border_color": "#E2E8F0"})
        body = wb.add_format({"border": 1, "border_color": "#E2E8F0"})

        latest = panel.sort_values("periodo_mes").groupby(["codigo_proyecto", "proyecto"], as_index=False).tail(1)
        summary_cols = [
            "proyecto",
            "stock_total_departamentos_actual_ref",
            "stock_ofertado_observado_acum",
            "cobertura_oferta_ledger_vs_universo_actual",
            "saldo_final_observado",
            "absorcion_neta_mes",
            "absorcion_neta_6m",
            "absorcion_stock_acumulada_observada",
        ]
        ws = wb.add_worksheet("ACUMULADO")
        writer.sheets["ACUMULADO"] = ws
        ws.merge_range(0, 0, 0, len(summary_cols)-1, "ABSORCIÓN ECONÓMICA · RESUMEN MULTIPROYECTO", title)
        ws.write(1, 0, f"Actualizado al {generated:%d/%m/%Y}", note)
        ws.write(2, 0, "STOCK TOTAL PROYECTO = universo actual completo de departamentos (referencia); no se presenta como stock histórico de lanzamiento.", note)
        headers = ["PROYECTO", "STOCK TOTAL PROYECTO REF.", "STOCK OFERTADO OBS. ACUM.", "COBERTURA LEDGER", "SALDO FINAL OBS.", "ABS. NETA MES", "ABS. NETA 6M", "ABS. STOCK ACUM."]
        for c, h in enumerate(headers):
            ws.write(4, c, h, header)
        for r, (_, row) in enumerate(latest[summary_cols].iterrows(), start=5):
            ws.write(r, 0, row["proyecto"], body)
            ws.write(r, 1, row["stock_total_departamentos_actual_ref"], integer)
            ws.write(r, 2, row["stock_ofertado_observado_acum"], integer)
            ws.write(r, 3, row["cobertura_oferta_ledger_vs_universo_actual"], pct)
            ws.write(r, 4, row["saldo_final_observado"], integer)
            ws.write(r, 5, row["absorcion_neta_mes"], pct)
            ws.write(r, 6, row["absorcion_neta_6m"], pct)
            ws.write(r, 7, row["absorcion_stock_acumulada_observada"], pct)
        ws.set_column("A:A", 24)
        ws.set_column("B:H", 22)
        ws.freeze_panes(5, 1)
        ws.hide_gridlines(2)

        display_headers = [
            "PERIODO",
            "STOCK TOTAL PROYECTO REF.",
            "STOCK INICIO OBS.",
            "ALTAS MES",
            "ALTAS ACUM. LEDGER",
            "STOCK OFERTADO OBS. ACUM.",
            "COBERTURA LEDGER",
            "SEPARACIONES",
            "CAÍDAS",
            "MOV. NETO",
            "VENDIDAS / MINUTAS",
            "SALDO FINAL OBS.",
            "ABS. BRUTA MES",
            "ABS. NETA MES",
            "ABS. NETA 6M",
            "ABS. STOCK ACUM.",
            "EDAD COMERCIAL MESES",
        ]
        for project, g in panel.groupby("proyecto"):
            g = g.sort_values("periodo_mes").copy()
            name = _sheet_name(project)
            ws = wb.add_worksheet(name)
            writer.sheets[name] = ws
            ws.merge_range(0, 0, 0, len(cols)-1, f"ABSORCIÓN ECONÓMICA · {project}", title)
            ws.write(1, 0, f"Actualizado al {generated:%d/%m/%Y}", note)
            ws.write(2, 0, "Referencia completa actual + historia observada del ledger. ALTAS ACUMULADAS no resta caídas: las caídas son reingresos, no nuevas altas.", note)
            for c, h in enumerate(display_headers):
                ws.write(4, c, h, header)
            for rr, (_, row) in enumerate(g[cols].iterrows(), start=5):
                ws.write_datetime(rr, 0, pd.Timestamp(row["periodo_mes"]).to_pydatetime(), wb.add_format({"num_format": "mmm yyyy", "border": 1, "border_color": "#E2E8F0"}))
                for c in [1,2,3,4,5,7,8,9,10,11,16]:
                    ws.write(rr, c, row.iloc[c], integer)
                for c in [6,12,13,14,15]:
                    value = row.iloc[c]
                    if pd.isna(value):
                        ws.write_blank(rr, c, None, pct)
                    else:
                        ws.write(rr, c, value, pct)
            ws.set_column("A:A", 14)
            ws.set_column("B:Q", 19)
            ws.freeze_panes(5, 1)
            ws.autofilter(4, 0, 4 + len(g), len(cols)-1)
            ws.hide_gridlines(2)

        ws = wb.add_worksheet("CONTRATO")
        writer.sheets["CONTRATO"] = ws
        ws.write(0, 0, "Métrica", header)
        ws.write(0, 1, "Definición", header)
        contract = [
            ("STOCK TOTAL PROYECTO REF.", "Conteo actual completo de departamentos en core.dim_unidad. Referencia estructural, no back-cast histórico."),
            ("ALTAS ACUM. LEDGER", "Suma acumulada de ALTA_STOCK observada. No descuenta caídas porque una caída reingresa stock, no crea una nueva unidad."),
            ("STOCK OFERTADO OBS. ACUM.", "Stock inicial observado del ledger + altas acumuladas observadas."),
            ("COBERTURA LEDGER", "Stock ofertado observado acumulado / stock total actual de departamentos."),
            ("ABS. NETA MES", "(separaciones efectivas - caídas efectivas) / stock inicio observado."),
            ("ABS. STOCK ACUM.", "(stock ofertado observado acumulado - saldo final observado) / stock ofertado observado acumulado."),
        ]
        for i, item in enumerate(contract, start=1):
            ws.write(i, 0, item[0], body)
            ws.write(i, 1, item[1], body)
        ws.set_column("A:A", 30)
        ws.set_column("B:B", 90)

    return path
