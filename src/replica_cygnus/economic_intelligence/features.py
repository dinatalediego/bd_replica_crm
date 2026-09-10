from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureSets:
    safe_numeric: tuple[str, ...]
    macro_numeric: tuple[str, ...]
    reference_only: tuple[str, ...]


def model_feature_sets() -> FeatureSets:
    """Feature contract.

    `reference_only` contains current-state variables useful for diagnostics and
    scenarios but excluded from historical training by default to avoid leakage.
    """
    return FeatureSets(
        safe_numeric=(
            "stock_inicio_observado",
            "saldo_final_observado",
            "altas_mes",
            "separaciones_brutas_mes",
            "caidas_mes",
            "ventas_minutas_mes",
            "mov_neto_lag1",
            "mov_neto_lag2",
            "mov_neto_lag3",
            "minutas_lag1",
            "absorcion_lag1",
            "mov_neto_ma3",
            "mov_neto_ma6",
            "absorcion_ma6",
            "edad_comercial_meses",
            "proyectos_activos_market",
            "stock_inicio_market",
            "altas_market",
            "demanda_neta_market",
            "minutas_market",
            "saldo_final_market",
            "absorcion_neta_market",
            "season_sin",
            "season_cos",
        ),
        macro_numeric=(
            "tasa_referencia_bcrp",
            "tasa_hipotecaria",
            "tc_usd_pen",
            "inflacion_yoy",
            "actividad_yoy",
            "desempleo",
        ),
        reference_only=(
            "stock_total_departamentos_actual_ref",
            "precio_lista_prom_actual_ref",
            "precio_lista_mediana_actual_ref",
            "precio_m2_prom_actual_ref",
            "descuento_prom_actual_ref",
            "cobertura_oferta_ledger_vs_universo_actual",
        ),
    )


def _future_sum(series: pd.Series, horizon: int) -> pd.Series:
    return sum(series.shift(-i) for i in range(1, horizon + 1))


def build_supervised_panel(panel: pd.DataFrame, horizons: tuple[int, ...] = (1, 3, 6)) -> pd.DataFrame:
    """Create project-month targets without using future values as predictors."""
    df = panel.sort_values(["codigo_proyecto", "periodo_mes"]).copy()
    grouped = df.groupby("codigo_proyecto", group_keys=False)

    for h in horizons:
        df[f"target_mov_neto_next_{h}m"] = grouped["movimiento_neto_mes"].transform(lambda s: _future_sum(s, h))
        df[f"target_minutas_next_{h}m"] = grouped["ventas_minutas_mes"].transform(lambda s: _future_sum(s, h))

    # Primary one-step targets used for recursive stock-out forecasting.
    df["target_mov_neto_next_1m"] = grouped["movimiento_neto_mes"].shift(-1)
    df["target_minutas_next_1m"] = grouped["ventas_minutas_mes"].shift(-1)

    # Useful economically interpretable transformations.
    df["stock_pressure"] = np.where(
        df["stock_inicio_observado"].fillna(0).gt(0),
        df["mov_neto_ma3"] / df["stock_inicio_observado"],
        np.nan,
    )
    df["market_share_demand"] = np.where(
        df["demanda_neta_market"].fillna(0).ne(0),
        df["movimiento_neto_mes"] / df["demanda_neta_market"],
        np.nan,
    )
    df["supply_coverage_gap_ref"] = (
        df["stock_total_departamentos_actual_ref"] - df["stock_ofertado_observado_acum"]
    )
    return df


def select_model_matrix(
    supervised: pd.DataFrame,
    target: str,
    include_macro: bool = True,
    include_reference: bool = False,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    sets = model_feature_sets()
    cols = list(sets.safe_numeric)
    if include_macro:
        cols.extend(sets.macro_numeric)
    if include_reference:
        cols.extend(sets.reference_only)
    cols.extend(["stock_pressure", "market_share_demand"])
    cols = [c for c in cols if c in supervised.columns]

    work = supervised.dropna(subset=[target]).copy()
    X = work[cols].replace([np.inf, -np.inf], np.nan)
    y = pd.to_numeric(work[target], errors="coerce")
    mask = y.notna()
    return X.loc[mask], y.loc[mask], cols
