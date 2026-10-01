from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .base import ProbabilityFamily
from .types import FamilyResult, LabContext
from .visualization import (
    plot_bayesian_groups,
    plot_calibration,
    plot_conversion_rate,
    plot_mixture,
    plot_survival,
)


def _closed_cycles(data: pd.DataFrame) -> pd.DataFrame:
    return data.loc[
        data["fecha_separacion"].notna() & data["outcome_observed"]
    ].copy()


class ConversionBinomialFamily(ProbabilityFamily):
    family_id = "conversion_binomial"
    title = "Bernoulli y Binomial · Conversión comercial"
    question = "¿Con qué probabilidad un ciclo cerrado termina en venta?"

    def run(self, ctx: LabContext) -> FamilyResult:
        data = _closed_cycles(ctx.data)
        n = len(data)
        if n == 0:
            return FamilyResult(
                self.family_id,
                self.title,
                self.question,
                limitations=["No existen ciclos cerrados con desenlace observado."],
            )

        successes = int(data["is_sale"].sum())
        rate = successes / n
        se = math.sqrt(rate * (1 - rate) / n)
        fig = plot_conversion_rate(
            rate, ctx.output_dir / "figures" / "01_conversion_binomial.png"
        )

        return FamilyResult(
            family_id=self.family_id,
            title=self.title,
            question=self.question,
            theory=[
                "Cada ciclo cerrado puede representarse como Bernoulli: venta=1 y caída/no venta=0.",
                "La suma de ensayos comparables conduce al modelo Binomial.",
                "La tasa observada es una estimación; su error estándar recuerda que existe incertidumbre muestral.",
            ],
            metrics={
                "n_ciclos_cerrados": n,
                "ventas": successes,
                "conversion_rate": rate,
                "standard_error": se,
            },
            insights=[
                "Esta familia define la unidad probabilística mínima del laboratorio.",
                "Los ciclos aún abiertos se excluyen para no etiquetar prematuramente una oportunidad como no venta.",
            ],
            limitations=[
                "Los ciclos pueden diferir por proyecto, asesor, tipología y periodo.",
                "Una tasa agregada no representa por sí sola heterogeneidad ni causalidad.",
            ],
            figures=[fig],
        )


class BayesianConversionFamily(ProbabilityFamily):
    family_id = "bayesian_conversion"
    title = "Beta–Binomial · Conversión e incertidumbre"
    question = "¿Qué tan probable es vender por grupo y qué tan segura es la estimación?"

    def run(self, ctx: LabContext) -> FamilyResult:
        cfg = ctx.config.get("bayesian_conversion", {})
        group_col = cfg.get("group_by", "codigo_proyecto")
        alpha0 = float(cfg.get("alpha_prior", 1.0))
        beta0 = float(cfg.get("beta_prior", 1.0))
        min_n = int(cfg.get("min_group_n", 8))

        rows = []
        data = _closed_cycles(ctx.data)
        for group, sample in data.groupby(group_col, dropna=False):
            n = len(sample)
            if n < min_n:
                continue
            sales = int(sample["is_sale"].sum())
            alpha_post = alpha0 + sales
            beta_post = beta0 + n - sales
            rows.append(
                {
                    "group": str(group),
                    "n": n,
                    "sales": sales,
                    "raw_rate": sales / n,
                    "posterior_mean": alpha_post / (alpha_post + beta_post),
                    "ci_low": beta_dist.ppf(0.025, alpha_post, beta_post),
                    "ci_high": beta_dist.ppf(0.975, alpha_post, beta_post),
                }
            )

        summary = pd.DataFrame(rows)
        if summary.empty:
            return FamilyResult(
                self.family_id,
                self.title,
                self.question,
                limitations=[f"No hay grupos con al menos {min_n} ciclos cerrados."],
            )

        fig = plot_bayesian_groups(
            summary, ctx.output_dir / "figures" / "02_bayesian_conversion.png"
        )
        out = ctx.output_dir / "experiments" / "bayesian_conversion.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(out, index=False)

        widest = summary.assign(
            width=summary["ci_high"] - summary["ci_low"]
        ).sort_values("width", ascending=False).iloc[0]

        return FamilyResult(
            family_id=self.family_id,
            title=self.title,
            question=self.question,
            theory=[
                "Beta es conjugada de Bernoulli/Binomial: prior y evidencia producen una posterior Beta.",
                "Grupos pequeños quedan más regularizados y muestran intervalos creíbles más amplios.",
                "La posterior separa nivel esperado de conversión y certeza sobre ese nivel.",
            ],
            metrics={
                "groups": int(len(summary)),
                "group_by": group_col,
                "largest_uncertainty_group": str(widest["group"]),
                "largest_uncertainty_width": float(widest["width"]),
            },
            insights=[
                "Una tasa alta con pocos casos no se trata como equivalente a una tasa similar con cientos de observaciones.",
                "El resultado puede reconfigurarse por proyecto, asesor u otra dimensión sin cambiar el motor.",
            ],
            limitations=[
                "El prior Beta(1,1) es deliberadamente simple para la V1.",
                "Diferencias posteriores entre grupos no demuestran efectos causales.",
            ],
            figures=[fig],
            artifacts={"summary_csv": str(out)},
        )


class TimeToEventFamily(ProbabilityFamily):
    family_id = "time_to_event"
    title = "Tiempo a evento · Duración del ciclo"
    question = "¿Cómo se distribuye el tiempo desde separación hasta venta o caída?"

    def run(self, ctx: LabContext) -> FamilyResult:
        data = ctx.data.loc[
            ctx.data["outcome_observed"]
            & ctx.data["days_to_outcome"].notna()
            & (ctx.data["days_to_outcome"] >= 0),
            ["days_to_outcome", "is_sale", "is_fall"],
        ].copy()

        if len(data) < 10:
            return FamilyResult(
                self.family_id,
                self.title,
                self.question,
                limitations=["No existen suficientes duraciones observadas."],
            )

        times = np.sort(data["days_to_outcome"].astype(float).to_numpy())
        unique_days = np.unique(times)
        curve = pd.DataFrame(
            {
                "day": unique_days,
                "survival": [float(np.mean(times > t)) for t in unique_days],
            }
        )
        fig = plot_survival(
            curve, ctx.output_dir / "figures" / "03_time_to_event.png"
        )

        return FamilyResult(
            family_id=self.family_id,
            title=self.title,
            question=self.question,
            theory=[
                "La probabilidad de venta ignora el reloj; el análisis de tiempo a evento incorpora duración.",
                "S(t)=P(T>t) describe la probabilidad de continuar sin desenlace después de t días.",
                "La V1 usa supervivencia empírica como puente pedagógico hacia Kaplan–Meier, hazards y Cox.",
            ],
            metrics={
                "n_observed_outcomes": int(len(data)),
                "median_days_to_outcome": float(np.median(times)),
                "median_days_to_sale": float(
                    data.loc[data["is_sale"], "days_to_outcome"].median()
                ) if data["is_sale"].any() else None,
                "median_days_to_fall": float(
                    data.loc[data["is_fall"], "days_to_outcome"].median()
                ) if data["is_fall"].any() else None,
            },
            insights=[
                "El tiempo permite detectar ciclos largos que una tasa binaria no distingue.",
                "La siguiente evolución natural es tratar formalmente la censura de ciclos todavía abiertos.",
            ],
            limitations=[
                "La curva V1 usa solo desenlaces observados; no es aún Kaplan–Meier con censura.",
                "Cambios comerciales entre periodos pueden modificar la distribución de duraciones.",
            ],
            figures=[fig],
        )


class PredictiveProbabilityFamily(ProbabilityFamily):
    family_id = "predictive_probability"
    title = "Clasificación probabilística · P(venta | X)"
    question = "¿Podemos estimar una probabilidad de venta usando información disponible al separar?"

    FEATURES = [
        "codigo_proyecto",
        "asesor",
        "tipo_unidad_principal",
        "days_stock_to_separation",
        "separation_month",
        "separation_weekday",
    ]

    def run(self, ctx: LabContext) -> FamilyResult:
        cfg = ctx.config.get("predictive_probability", {})
        min_rows = int(ctx.config.get("lab", {}).get("min_rows_for_modeling", 80))
        test_fraction = float(cfg.get("test_fraction", 0.25))

        data = _closed_cycles(ctx.data).sort_values("fecha_separacion").copy()
        features = [column for column in self.FEATURES if column in data.columns]
        X = data[features]
        y = data["is_sale"].astype(int)

        if len(data) < min_rows or y.nunique() < 2:
            return FamilyResult(
                self.family_id,
                self.title,
                self.question,
                limitations=[
                    f"Se requieren al menos {min_rows} ciclos cerrados y ambas clases."
                ],
            )

        split = max(1, int(len(data) * (1 - test_fraction)))
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]
        if y_train.nunique() < 2 or y_test.nunique() < 2:
            return FamilyResult(
                self.family_id,
                self.title,
                self.question,
                limitations=["El corte temporal no contiene ambas clases en train/test."],
            )

        categorical = [
            c for c in features
            if c in {"codigo_proyecto", "asesor", "tipo_unidad_principal"}
        ]
        numeric = [c for c in features if c not in categorical]

        prep = ColumnTransformer(
            [
                (
                    "cat",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    categorical,
                ),
                (
                    "num",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="median")),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    numeric,
                ),
            ]
        )

        model = Pipeline(
            [
                ("prep", prep),
                (
                    "model",
                    LogisticRegression(max_iter=1000, class_weight="balanced"),
                ),
            ]
        )
        model.fit(X_train, y_train)
        probability = model.predict_proba(X_test)[:, 1]

        metrics = {
            "train_n": int(len(X_train)),
            "test_n": int(len(X_test)),
            "roc_auc": float(roc_auc_score(y_test, probability)),
            "brier": float(brier_score_loss(y_test, probability)),
            "log_loss": float(log_loss(y_test, probability)),
        }

        frac_pos, mean_pred = calibration_curve(
            y_test,
            probability,
            n_bins=min(8, max(3, len(y_test) // 20)),
            strategy="quantile",
        )
        fig = plot_calibration(
            frac_pos,
            mean_pred,
            ctx.output_dir / "figures" / "04_logistic_calibration.png",
            "Logistic",
        )

        if cfg.get("use_xgboost_if_available", True):
            try:
                from xgboost import XGBClassifier

                transformed_train = prep.fit_transform(X_train)
                transformed_test = prep.transform(X_test)
                xgb = XGBClassifier(
                    n_estimators=250,
                    max_depth=4,
                    learning_rate=0.05,
                    subsample=0.9,
                    colsample_bytree=0.9,
                    random_state=ctx.random_state,
                    eval_metric="logloss",
                )
                xgb.fit(transformed_train, y_train)
                probability_xgb = xgb.predict_proba(transformed_test)[:, 1]
                metrics.update(
                    {
                        "xgb_roc_auc": float(
                            roc_auc_score(y_test, probability_xgb)
                        ),
                        "xgb_brier": float(
                            brier_score_loss(y_test, probability_xgb)
                        ),
                        "xgb_log_loss": float(
                            log_loss(y_test, probability_xgb)
                        ),
                    }
                )
            except Exception as exc:
                metrics["xgboost_status"] = f"omitido: {type(exc).__name__}"

        return FamilyResult(
            family_id=self.family_id,
            title=self.title,
            question=self.question,
            theory=[
                "La regresión logística devuelve probabilidades y modela log-odds.",
                "AUC mide capacidad de ordenamiento; Brier, log-loss y calibración evalúan la calidad probabilística.",
                "XGBoost actúa como benchmark no lineal, no como reemplazo automático del modelo probabilístico interpretable.",
            ],
            metrics=metrics,
            insights=[
                "El train/test respeta orden temporal para aproximarse a una predicción futura real.",
                "Solo se usan variables disponibles al momento de la separación y ciclos con desenlace observado.",
            ],
            limitations=[
                "La V1 no define todavía un horizonte fijo de predicción.",
                "Agregar variables posteriores a la separación produciría leakage y debe evitarse.",
            ],
            figures=[fig],
        )


class LatentSegmentsFamily(ProbabilityFamily):
    family_id = "latent_segments"
    title = "Gaussian Mixture · Estructura latente"
    question = "¿Existen perfiles de ciclos que emerjan sin una etiqueta previa?"

    def run(self, ctx: LabContext) -> FamilyResult:
        cfg = ctx.config.get("latent_segments", {})
        data = ctx.data[
            ["days_stock_to_separation", "separation_month", "separation_weekday"]
        ].copy()
        data = data.replace([np.inf, -np.inf], np.nan).dropna()
        data = data[data["days_stock_to_separation"] >= 0]

        if len(data) < 60:
            return FamilyResult(
                self.family_id,
                self.title,
                self.question,
                limitations=["Se requieren al menos 60 observaciones completas."],
            )

        X = StandardScaler().fit_transform(data)
        candidates = []
        for components in range(
            int(cfg.get("min_components", 2)),
            int(cfg.get("max_components", 5)) + 1,
        ):
            if len(data) <= components:
                continue
            model = GaussianMixture(
                n_components=components, random_state=ctx.random_state
            )
            model.fit(X)
            candidates.append((model.bic(X), model))

        _, best = min(candidates, key=lambda item: item[0])
        data["cluster"] = best.predict(X)
        fig = plot_mixture(
            data, ctx.output_dir / "figures" / "05_latent_segments.png"
        )
        counts = data["cluster"].value_counts().sort_index().to_dict()

        return FamilyResult(
            family_id=self.family_id,
            title=self.title,
            question=self.question,
            theory=[
                "Gaussian Mixture representa la población como combinación de distribuciones latentes.",
                "Cada componente define una densidad probabilística y no solo un centro geométrico.",
                "BIC penaliza complejidad para evitar añadir componentes sin suficiente evidencia.",
            ],
            metrics={
                "n": int(len(data)),
                "selected_components": int(best.n_components),
                "cluster_counts": {str(k): int(v) for k, v in counts.items()},
            },
            insights=[
                "Los clusters son hipótesis de perfiles y deben interpretarse cruzándolos con variables comerciales.",
                "Un segmento matemático no se convierte automáticamente en una política de negocio.",
            ],
            limitations=[
                "Los componentes dependen de la selección y escala de variables.",
                "La V1 es pedagógica; una segmentación operativa requeriría estabilidad temporal y validación externa.",
            ],
            figures=[fig],
        )
