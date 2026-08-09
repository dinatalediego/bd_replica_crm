from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


@dataclass(frozen=True)
class ForecastResult:
    forecast: pd.DataFrame
    residual_std: float


def forecast_monthly_series(
    series: pd.Series,
    periods: int = 6,
    seasonal_periods: int = 12,
    confidence: float = 0.90,
) -> ForecastResult:
    """Baseline ETS con intervalo aproximado basado en residuos históricos."""
    clean = series.dropna().astype(float).sort_index()
    if len(clean) < max(8, seasonal_periods + 2):
        raise ValueError("Se requieren más observaciones para un forecast mensual estable")
    use_seasonal = len(clean) >= 2 * seasonal_periods
    model = ExponentialSmoothing(
        clean,
        trend="add",
        seasonal="add" if use_seasonal else None,
        seasonal_periods=seasonal_periods if use_seasonal else None,
        initialization_method="estimated",
    ).fit(optimized=True)
    point = model.forecast(periods)
    residual_std = float(np.nanstd(model.resid, ddof=1))
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    horizon = np.arange(1, periods + 1, dtype=float)
    # Intervalo deliberadamente conservador que crece con sqrt(h).
    margin = z * residual_std * np.sqrt(horizon)
    out = pd.DataFrame(
        {
            "forecast": point.values,
            "lower": point.values - margin,
            "upper": point.values + margin,
        },
        index=point.index,
    )
    return ForecastResult(forecast=out, residual_std=residual_std)
