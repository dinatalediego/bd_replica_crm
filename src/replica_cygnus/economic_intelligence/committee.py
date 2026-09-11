from __future__ import annotations

import numpy as np
import pandas as pd


def _trend_label(current: float | None, prior: float | None, tolerance: float = 0.01) -> str:
    if current is None or prior is None or pd.isna(current) or pd.isna(prior):
        return "SIN COMPARABLE"
    delta = float(current) - float(prior)
    if delta > tolerance:
        return "ACELERA"
    if delta < -tolerance:
        return "DESACELERA"
    return "ESTABLE"


def build_committee_brief(
    panel: pd.DataFrame,
    forecast_summary: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One-row-per-project decision table for CEO/PMO review.

    It converts analytics into explicit attention flags without pretending that
    the recommendation is an autonomous commercial decision.
    """
    if panel.empty:
        return pd.DataFrame()

    rows = []
    forecast_lookup = {}
    if forecast_summary is not None and not forecast_summary.empty and "codigo_proyecto" in forecast_summary:
        forecast_lookup = {
            str(r["codigo_proyecto"]): r
            for _, r in forecast_summary.iterrows()
        }

    for code, group in panel.sort_values("periodo_mes").groupby("codigo_proyecto"):
        g = group.sort_values("periodo_mes")
        latest = g.iloc[-1]
        prior = g.iloc[-2] if len(g) > 1 else latest
        stock = float(latest.get("saldo_final_observado", np.nan))
        ma3 = float(latest.get("mov_neto_ma3", np.nan))
        months_stock = stock / ma3 if np.isfinite(stock) and np.isfinite(ma3) and ma3 > 0 else np.nan
        absorption = latest.get("absorcion_neta_mes")
        absorption_ma6 = latest.get("absorcion_ma6")
        falls = latest.get("caidas_mes")
        coverage = latest.get("cobertura_oferta_ledger_vs_universo_actual")

        flags = []
        if np.isfinite(months_stock) and months_stock > 12:
            flags.append("STOCK LENTO")
        if pd.notna(absorption) and pd.notna(absorption_ma6) and float(absorption) < float(absorption_ma6) * 0.7:
            flags.append("ABSORCIÓN BAJO TENDENCIA")
        if pd.notna(falls) and float(falls) >= 3:
            flags.append("CAÍDAS ALTAS")
        if pd.notna(coverage) and float(coverage) < 0.8:
            flags.append("LEDGER INCOMPLETO")

        f = forecast_lookup.get(str(code), {})
        rows.append({
            "codigo_proyecto": code,
            "proyecto": latest.get("proyecto", code),
            "periodo_ultimo": latest.get("periodo_mes"),
            "stock_actual_observado": latest.get("saldo_final_observado"),
            "stock_total_actual_ref": latest.get("stock_total_departamentos_actual_ref"),
            "absorcion_neta_mes": absorption,
            "absorcion_ma6": absorption_ma6,
            "tendencia_absorcion": _trend_label(absorption, prior.get("absorcion_neta_mes")),
            "mov_neto_ma3": latest.get("mov_neto_ma3"),
            "meses_stock_a_ritmo_ma3": months_stock,
            "minutas_mes": latest.get("ventas_minutas_mes"),
            "caidas_mes": falls,
            "absorcion_stock_acum": latest.get("absorcion_stock_acumulada_observada"),
            "cobertura_oferta_ledger": coverage,
            "forecast_demanda_neta_3m": f.get("forecast_demanda_neta_3m", np.nan) if hasattr(f, "get") else np.nan,
            "forecast_demanda_neta_6m": f.get("forecast_demanda_neta_6m", np.nan) if hasattr(f, "get") else np.nan,
            "mes_stockout_p50": f.get("mes_stockout_p50", pd.NaT) if hasattr(f, "get") else pd.NaT,
            "prioridad_pmo": "ALTA" if len(flags) >= 2 else ("MEDIA" if flags else "NORMAL"),
            "banderas": " · ".join(flags) if flags else "SIN ALERTA MATERIAL",
        })

    return pd.DataFrame(rows).sort_values(["prioridad_pmo", "meses_stock_a_ritmo_ma3"], ascending=[True, False])
