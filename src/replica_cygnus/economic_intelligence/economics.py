from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def build_market_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Market-level endogenous macro panel from all projects in Medallio."""
    if panel.empty:
        return panel.copy()
    agg = (
        panel.groupby("periodo_mes", as_index=False)
        .agg(
            proyectos_activos=("codigo_proyecto", "nunique"),
            stock_inicio=("stock_inicio_observado", "sum"),
            altas=("altas_mes", "sum"),
            demanda_neta=("movimiento_neto_mes", "sum"),
            minutas=("ventas_minutas_mes", "sum"),
            saldo_final=("saldo_final_observado", "sum"),
            precio_m2_prom_actual_ref=("precio_m2_prom_actual_ref", "mean"),
            descuento_prom_actual_ref=("descuento_prom_actual_ref", "mean"),
        )
        .sort_values("periodo_mes")
    )
    agg["absorcion_neta_market"] = agg["demanda_neta"] / agg["stock_inicio"].replace(0, np.nan)
    agg["supply_demand_ratio"] = agg["stock_inicio"] / agg["demanda_neta"].replace(0, np.nan)
    agg["demanda_ma3"] = agg["demanda_neta"].rolling(3, min_periods=1).mean()
    agg["demanda_ma6"] = agg["demanda_neta"].rolling(6, min_periods=1).mean()
    agg["stock_meses_demanda_ma3"] = agg["saldo_final"] / agg["demanda_ma3"].replace(0, np.nan)
    return agg


def cluster_project_regimes(
    panel: pd.DataFrame,
    features: Iterable[str] | None = None,
    n_clusters: int = 4,
    random_state: int = 42,
) -> tuple[pd.DataFrame, object, object]:
    """Discover latent project-month commercial regimes; descriptive, not causal."""
    default = [
        "absorcion_neta_mes",
        "mov_neto_ma3",
        "caidas_mes",
        "ventas_minutas_mes",
        "stock_inicio_observado",
        "edad_comercial_meses",
        "absorcion_neta_market",
    ]
    cols = [c for c in (features or default) if c in panel.columns]
    work = panel.dropna(subset=["periodo_mes", "codigo_proyecto"]).copy()
    X = work[cols].replace([np.inf, -np.inf], np.nan)

    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("cluster", KMeans(n_clusters=n_clusters, n_init=20, random_state=random_state)),
    ])
    labels = pipe.fit_predict(X)
    out = work[[c for c in ["periodo_mes", "codigo_proyecto", "proyecto"] if c in work.columns]].copy()
    out["regime_cluster"] = labels

    pca_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("pca", PCA(n_components=min(2, len(cols)))),
    ])
    coords = pca_pipe.fit_transform(X)
    if coords.shape[1] >= 1:
        out["latent_factor_1"] = coords[:, 0]
    if coords.shape[1] >= 2:
        out["latent_factor_2"] = coords[:, 1]
    return out, pipe, pca_pipe


def finite_difference_gradients(
    model: object,
    X: pd.DataFrame,
    features: Iterable[str],
    relative_step: float = 0.01,
) -> pd.DataFrame:
    """Numerical marginal response of predictions to features.

    These are model sensitivities, not causal elasticities. They are useful as
    a bridge from a black-box prediction to executive interpretation.
    """
    rows = []
    base = X.copy()
    base_pred = np.asarray(model.predict(base), dtype=float)
    for feature in features:
        if feature not in base.columns:
            continue
        x = pd.to_numeric(base[feature], errors="coerce")
        scale = float(np.nanmedian(np.abs(x)))
        eps = max(scale * relative_step, relative_step)
        plus = base.copy()
        minus = base.copy()
        plus[feature] = x + eps
        minus[feature] = x - eps
        p_plus = np.asarray(model.predict(plus), dtype=float)
        p_minus = np.asarray(model.predict(minus), dtype=float)
        grad = (p_plus - p_minus) / (2 * eps)
        rows.append({
            "feature": feature,
            "gradient_mean": float(np.nanmean(grad)),
            "gradient_median": float(np.nanmedian(grad)),
            "gradient_abs_mean": float(np.nanmean(np.abs(grad))),
            "base_prediction_mean": float(np.nanmean(base_pred)),
            "interpretation": "model sensitivity; not causal",
        })
    return pd.DataFrame(rows).sort_values("gradient_abs_mean", ascending=False)


def price_area_indifference_proxy(
    area_values: Iterable[float],
    budgets: Iterable[float],
) -> pd.DataFrame:
    """Simple iso-budget curves (price/m2 = budget/area), not structural utility curves."""
    rows = []
    for budget in budgets:
        for area in area_values:
            a = float(area)
            rows.append({
                "budget": float(budget),
                "area_m2": a,
                "price_m2_iso_budget": float(budget) / a if a > 0 else np.nan,
            })
    return pd.DataFrame(rows)
