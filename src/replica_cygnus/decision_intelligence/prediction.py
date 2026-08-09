from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


@dataclass
class BinaryPredictionModel:
    pipeline: Pipeline
    numeric_features: list[str]
    categorical_features: list[str]
    target: str
    auc: float | None = None
    brier: float | None = None

    def predict_probability(self, data: pd.DataFrame) -> pd.Series:
        features = self.numeric_features + self.categorical_features
        probabilities = self.pipeline.predict_proba(data[features])[:, 1]
        return pd.Series(probabilities, index=data.index, name="predicted_probability")


def train_binary_logistic_model(
    train: pd.DataFrame,
    target: str,
    numeric_features: list[str],
    categorical_features: list[str] | None = None,
    validation: pd.DataFrame | None = None,
) -> BinaryPredictionModel:
    """Baseline interpretable y reproducible para probabilidad de un evento binario."""
    categorical_features = list(categorical_features or [])
    features = list(numeric_features) + categorical_features
    missing = set(features + [target]) - set(train.columns)
    if missing:
        raise ValueError(f"Faltan columnas de entrenamiento: {', '.join(sorted(missing))}")

    numeric_pipe = Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocessor = ColumnTransformer(
        [
            ("num", numeric_pipe, numeric_features),
            ("cat", categorical_pipe, categorical_features),
        ],
        remainder="drop",
    )
    pipeline = Pipeline(
        [
            ("preprocess", preprocessor),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ]
    )
    pipeline.fit(train[features], train[target].astype(int))
    result = BinaryPredictionModel(
        pipeline=pipeline,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        target=target,
    )

    if validation is not None and len(validation) > 0:
        y = validation[target].astype(int)
        p = result.predict_probability(validation)
        result.brier = float(brier_score_loss(y, p))
        result.auc = float(roc_auc_score(y, p)) if y.nunique() > 1 else None
    return result
