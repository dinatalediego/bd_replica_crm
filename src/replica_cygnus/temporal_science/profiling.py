from __future__ import annotations

from dataclasses import dataclass
import math
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller, kpss


@dataclass(frozen=True)
class ModelRecommendation:
    model_family: str
    eligible: bool
    score: float
    deployment_role: str
    reasons: tuple[str, ...]
    requirements: dict

    def as_dict(self) -> dict:
        return {
            "model_family": self.model_family,
            "eligible": self.eligible,
            "suitability_score": float(max(0.0, min(100.0, self.score))),
            "deployment_role": self.deployment_role,
            "reasons": list(self.reasons),
            "requirements": self.requirements,
        }


def _safe_float(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _corr(values: np.ndarray, lag: int) -> float | None:
    if len(values) <= lag:
        return None
    left, right = values[:-lag], values[lag:]
    if np.nanstd(left) == 0 or np.nanstd(right) == 0:
        return None
    return _safe_float(np.corrcoef(left, right)[0, 1])


def _stationarity(values: np.ndarray) -> tuple[float | None, float | None]:
    clean = values[np.isfinite(values)]
    if len(clean) < 12 or np.nanstd(clean) == 0:
        return None, None
    adf_p = kpss_p = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            adf_p = _safe_float(adfuller(clean, autolag="AIC")[1])
        except (ValueError, np.linalg.LinAlgError):
            pass
        try:
            kpss_p = _safe_float(kpss(clean, regression="c", nlags="auto")[1])
        except (ValueError, np.linalg.LinAlgError, OverflowError):
            pass
    return adf_p, kpss_p


def _seasonal_strength(values: np.ndarray, period: int = 12) -> float | None:
    clean = values[np.isfinite(values)]
    if len(clean) < 2 * period or np.nanstd(clean) == 0:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            fit = STL(clean, period=period, robust=True).fit()
            resid = np.asarray(fit.resid, dtype=float)
            seasonal = np.asarray(fit.seasonal, dtype=float)
            denom = np.var(resid + seasonal)
            if denom <= 0:
                return None
            return _safe_float(max(0.0, min(1.0, 1.0 - np.var(resid) / denom)))
        except (ValueError, np.linalg.LinAlgError):
            return None


def _demand_pattern(values: np.ndarray) -> tuple[float | None, float | None, str | None]:
    clean = values[np.isfinite(values)]
    positive = clean[clean > 0]
    if len(clean) == 0 or len(positive) == 0:
        return None, None, "ALL_ZERO"
    adi = len(clean) / len(positive)
    mean_positive = positive.mean()
    cv2 = float((positive.std(ddof=1) / mean_positive) ** 2) if len(positive) > 1 and mean_positive else 0.0
    if adi < 1.32 and cv2 < 0.49:
        pattern = "SMOOTH"
    elif adi < 1.32 and cv2 >= 0.49:
        pattern = "ERRATIC"
    elif adi >= 1.32 and cv2 < 0.49:
        pattern = "INTERMITTENT"
    else:
        pattern = "LUMPY"
    return _safe_float(adi), _safe_float(cv2), pattern


def _quantile(series: pd.Series, q: float) -> float | None:
    value = series.quantile(q)
    return _safe_float(value)


def profile_numeric(series: pd.Series) -> dict:
    numeric = pd.to_numeric(series, errors="coerce")
    n = int(len(numeric))
    valid = numeric.dropna()
    if not len(valid):
        return {
            "observations": n,
            "null_rate": 1.0 if n else None,
            "zero_rate": None,
            "mean_value": None,
            "std_value": None,
            "min_value": None,
            "q05": None,
            "q25": None,
            "median": None,
            "q75": None,
            "q95": None,
            "max_value": None,
            "skewness": None,
            "kurtosis": None,
        }
    return {
        "observations": n,
        "null_rate": _safe_float(numeric.isna().mean()),
        "zero_rate": _safe_float(valid.eq(0).mean()),
        "mean_value": _safe_float(valid.mean()),
        "std_value": _safe_float(valid.std(ddof=1)) if len(valid) > 1 else 0.0,
        "min_value": _safe_float(valid.min()),
        "q05": _quantile(valid, 0.05),
        "q25": _quantile(valid, 0.25),
        "median": _quantile(valid, 0.50),
        "q75": _quantile(valid, 0.75),
        "q95": _quantile(valid, 0.95),
        "max_value": _safe_float(valid.max()),
        "skewness": _safe_float(valid.skew()) if len(valid) > 2 else None,
        "kurtosis": _safe_float(valid.kurt()) if len(valid) > 3 else None,
    }


def profile_series(frame: pd.DataFrame, *, date_col: str, value_col: str, monthly: bool = True) -> dict:
    if date_col not in frame or value_col not in frame:
        raise ValueError(f"Missing {date_col!r} or {value_col!r}")
    d = frame[[date_col, value_col]].copy()
    d[date_col] = pd.to_datetime(d[date_col], errors="raise")
    d[value_col] = pd.to_numeric(d[value_col], errors="coerce")
    d = d.sort_values(date_col).drop_duplicates(date_col, keep="last")
    base = profile_numeric(d[value_col])
    valid = d.dropna(subset=[value_col])
    values = valid[value_col].to_numpy(dtype=float)
    base.update(
        observed_from=valid[date_col].min().date() if len(valid) else None,
        observed_to=valid[date_col].max().date() if len(valid) else None,
        missing_periods=0,
        acf1=_corr(values, 1),
        acf12=_corr(values, 12) if monthly else None,
        trend_slope=None,
        seasonal_strength=_seasonal_strength(values, 12) if monthly else None,
        adi=None,
        cv2=None,
        demand_pattern=None,
        adf_pvalue=None,
        kpss_pvalue=None,
    )
    if len(valid) >= 2:
        x = np.arange(len(valid), dtype=float)
        base["trend_slope"] = _safe_float(np.polyfit(x, values, 1)[0])
    if monthly and len(d):
        expected = pd.date_range(d[date_col].min().to_period("M").to_timestamp(), d[date_col].max().to_period("M").to_timestamp(), freq="MS")
        actual = set(d[date_col].dt.to_period("M").dt.to_timestamp())
        base["missing_periods"] = int(sum(ts not in actual for ts in expected))
    adi, cv2, pattern = _demand_pattern(values)
    base["adi"], base["cv2"], base["demand_pattern"] = adi, cv2, pattern
    adf_p, kpss_p = _stationarity(values)
    base["adf_pvalue"], base["kpss_pvalue"] = adf_p, kpss_p
    return base


def recommend_models(profile: dict, *, has_exogenous: bool = False, hierarchy: bool = True) -> list[dict]:
    n = int(profile.get("observations") or 0)
    zero = float(profile.get("zero_rate") or 0.0)
    seasonal = profile.get("seasonal_strength")
    pattern = profile.get("demand_pattern")
    missing = int(profile.get("missing_periods") or 0)
    recs: list[ModelRecommendation] = []

    recs.append(ModelRecommendation(
        "moving_average_3", n >= 3, 100 if n >= 3 else 20,
        "BASELINE" if n >= 3 else "NOT_ELIGIBLE",
        ("Simple, auditable reference required before promotion.",) if n >= 3 else ("Needs at least 3 observations.",),
        {"min_observations": 3},
    ))

    seasonal_ok = n >= 24 and missing == 0
    recs.append(ModelRecommendation(
        "seasonal_naive_12", seasonal_ok,
        75 + (10 if seasonal is not None and seasonal >= 0.35 else 0) if seasonal_ok else 25,
        "CANDIDATE" if seasonal_ok else "NOT_ELIGIBLE",
        ("At least two annual cycles are available.",) if seasonal_ok else ("Requires 24 complete monthly observations.",),
        {"min_observations": 24, "requires_complete_months": True},
    ))

    ets_ok = n >= 8 and zero < 0.8 and missing == 0
    recs.append(ModelRecommendation(
        "ets", ets_ok,
        80 + (5 if seasonal is not None and seasonal >= 0.25 else 0) if ets_ok else 30,
        "CANDIDATE" if ets_ok else "NOT_ELIGIBLE",
        tuple(r for r in [
            "Enough history for level/trend estimation." if n >= 8 else "Needs at least 8 observations.",
            "Very high zero inflation weakens ETS." if zero >= 0.8 else None,
            "Calendar gaps must be fixed before fitting." if missing else None,
        ] if r),
        {"min_observations": 8, "max_zero_rate": 0.8},
    ))

    intermittent = pattern in {"INTERMITTENT", "LUMPY", "ALL_ZERO"}
    croston_ok = n >= 12 and intermittent and missing == 0
    recs.append(ModelRecommendation(
        "croston_sba", croston_ok, 88 if croston_ok else 35,
        "CANDIDATE" if croston_ok else "NOT_ELIGIBLE",
        (f"Demand pattern is {pattern}; intermittent-demand methods deserve direct comparison.",) if croston_ok
        else ("Best reserved for intermittent/lumpy count series with >=12 complete periods.",),
        {"min_observations": 12, "patterns": ["INTERMITTENT", "LUMPY"]},
    ))

    sarimax_ok = n >= 36 and not intermittent and missing == 0
    sarimax_score = 82 + (8 if has_exogenous else 0) if sarimax_ok else 30
    recs.append(ModelRecommendation(
        "dynamic_regression_sarimax", sarimax_ok, sarimax_score,
        "CANDIDATE" if sarimax_ok else "NOT_ELIGIBLE",
        tuple(r for r in [
            "Three annual cycles support richer dynamics." if n >= 36 else "Needs roughly 36 monthly observations.",
            "Time-stamped exogenous variables are available." if has_exogenous and sarimax_ok else None,
            "Do not use current/future exogenous values that were unavailable at the origin." if sarimax_ok else None,
        ] if r),
        {"min_observations": 36, "point_in_time_exogenous_required": has_exogenous},
    ))

    global_ok = n >= 12 and missing == 0
    recs.append(ModelRecommendation(
        "global_tree_lags", global_ok, 76 if global_ok else 25,
        "SHADOW" if global_ok else "NOT_ELIGIBLE",
        ("Useful when pooled across projects; evaluate by time and project, never random row split.",) if global_ok
        else ("Needs regular lagged histories and portfolio support.",),
        {"pooled_model": True, "temporal_split": True, "project_guard": True},
    ))

    if hierarchy:
        hierarchy_ok = n >= 12
        recs.append(ModelRecommendation(
            "hierarchical_reconciliation", hierarchy_ok, 72 if hierarchy_ok else 20,
            "SHADOW" if hierarchy_ok else "NOT_ELIGIBLE",
            ("Reconcile portfolio/project/segment forecasts after each level has a validated base model.",) if hierarchy_ok
            else ("Requires stable hierarchy and base forecasts.",),
            {"requires_base_forecasts": True, "coherence_required": True},
        ))

    return [r.as_dict() for r in recs]


def population_stability_index(reference: pd.Series, current: pd.Series, bins: int = 6) -> float | None:
    ref = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    cur = pd.to_numeric(current, errors="coerce").dropna().to_numpy(dtype=float)
    if len(ref) < 10 or len(cur) < 5:
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0 if np.isclose(np.mean(ref), np.mean(cur)) else None
    edges[0], edges[-1] = -np.inf, np.inf
    ref_hist, _ = np.histogram(ref, bins=edges)
    cur_hist, _ = np.histogram(cur, bins=edges)
    eps = 1e-6
    ref_pct = np.maximum(ref_hist / max(ref_hist.sum(), 1), eps)
    cur_pct = np.maximum(cur_hist / max(cur_hist.sum(), 1), eps)
    return _safe_float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
