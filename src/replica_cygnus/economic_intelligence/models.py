from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass
class ModelResult:
    name: str
    model: object
    mae: float
    rmse: float
    smape: float
    n_train: int
    n_test: int


def _smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    den = np.abs(y_true) + np.abs(y_pred)
    ratio = np.zeros_like(den, dtype=float)
    np.divide(
        2 * np.abs(y_pred - y_true),
        den,
        out=ratio,
        where=den != 0,
    )
    return float(np.nanmean(ratio))


def _split_by_time(meta: pd.DataFrame, test_months: int = 6) -> tuple[pd.Index, pd.Index]:
    months = pd.Series(pd.to_datetime(meta["periodo_mes"]).dropna().unique()).sort_values()
    if len(months) < max(4, test_months + 2):
        cut = max(1, int(len(meta) * 0.8))
        return meta.index[:cut], meta.index[cut:]
    test_set = set(months.iloc[-test_months:])
    is_test = pd.to_datetime(meta["periodo_mes"]).isin(test_set)
    return meta.index[~is_test], meta.index[is_test]


def candidate_models(nonnegative_target: bool = False, random_state: int = 42) -> dict[str, object]:
    models: dict[str, object] = {
        "ridge": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=2.0)),
        ]),
        "hist_gradient_boosting": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", HistGradientBoostingRegressor(
                learning_rate=0.05,
                max_iter=250,
                max_leaf_nodes=15,
                l2_regularization=1.0,
                random_state=random_state,
            )),
        ]),
        "random_forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(
                n_estimators=350,
                min_samples_leaf=3,
                max_features=0.8,
                random_state=random_state,
                n_jobs=-1,
            )),
        ]),
    }
    if nonnegative_target:
        models["poisson"] = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", PoissonRegressor(alpha=0.5, max_iter=1000)),
        ])
    return models


def backtest_regressors(
    X: pd.DataFrame,
    y: pd.Series,
    meta: pd.DataFrame,
    *,
    nonnegative_target: bool = False,
    test_months: int = 6,
) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    """Hold out the most recent calendar months across all projects."""
    common = X.index.intersection(y.index).intersection(meta.index)
    X = X.loc[common]
    y = y.loc[common].astype(float)
    meta = meta.loc[common].copy()
    train_idx, test_idx = _split_by_time(meta, test_months=test_months)

    results: list[ModelResult] = []
    fitted: dict[str, object] = {}
    pred_frames: list[pd.DataFrame] = []

    for name, model in candidate_models(nonnegative_target=nonnegative_target).items():
        y_train = y.loc[train_idx]
        if nonnegative_target:
            y_train = y_train.clip(lower=0)
        model.fit(X.loc[train_idx], y_train)
        pred = np.asarray(model.predict(X.loc[test_idx]), dtype=float)
        if nonnegative_target:
            pred = np.clip(pred, 0, None)
        actual = y.loc[test_idx].to_numpy(dtype=float)
        results.append(ModelResult(
            name=name,
            model=model,
            mae=float(mean_absolute_error(actual, pred)),
            rmse=float(mean_squared_error(actual, pred) ** 0.5),
            smape=_smape(actual, pred),
            n_train=len(train_idx),
            n_test=len(test_idx),
        ))
        fitted[name] = model
        tmp = meta.loc[test_idx, [c for c in ["periodo_mes", "codigo_proyecto", "proyecto"] if c in meta.columns]].copy()
        tmp["actual"] = actual
        tmp["pred"] = pred
        tmp["model"] = name
        pred_frames.append(tmp)

    scores = pd.DataFrame([r.__dict__ | {"model": None} for r in results]).drop(columns=["model"])
    scores = scores.sort_values(["mae", "rmse"]).reset_index(drop=True)
    predictions = pd.concat(pred_frames, ignore_index=True) if pred_frames else pd.DataFrame()
    return scores, fitted, predictions


def fit_champion_model(
    X: pd.DataFrame,
    y: pd.Series,
    model_name: str = "hist_gradient_boosting",
    nonnegative_target: bool = False,
) -> object:
    model = candidate_models(nonnegative_target=nonnegative_target)[model_name]
    target = y.astype(float).clip(lower=0) if nonnegative_target else y.astype(float)
    model.fit(X, target)
    return model


def forecast_stockout_path(
    current_stock: float,
    monthly_net_demand: Iterable[float],
    start_period: pd.Timestamp | str,
) -> pd.DataFrame:
    """Translate predicted net stock exits into a transparent depletion path."""
    stock = max(float(current_stock), 0.0)
    period = pd.Timestamp(start_period).to_period("M")
    rows = []
    for step, demand in enumerate(monthly_net_demand, start=1):
        d = max(float(demand), 0.0)
        sold = min(stock, d)
        end_stock = max(stock - sold, 0.0)
        rows.append({
            "horizon_month": step,
            "periodo": (period + step).to_timestamp(),
            "stock_inicio_pred": stock,
            "demanda_neta_pred": d,
            "unidades_absorbidas_pred": sold,
            "stock_fin_pred": end_stock,
            "agotado": end_stock <= 0,
        })
        stock = end_stock
    return pd.DataFrame(rows)
