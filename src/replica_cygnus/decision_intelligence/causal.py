from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.formula.api as smf


@dataclass(frozen=True)
class DifferenceInDifferencesResult:
    treatment_effect: float
    standard_error: float
    p_value: float
    confidence_low: float
    confidence_high: float
    n_obs: int


def estimate_difference_in_differences(
    data: pd.DataFrame,
    outcome: str,
    treated: str,
    post: str,
    controls: list[str] | None = None,
) -> DifferenceInDifferencesResult:
    """Estimador DiD transparente para una primera capa causal.

    Requiere que `treated` y `post` sean indicadores 0/1. La función no hace
    que el diseño sea causal por sí solo: el supuesto de tendencias paralelas
    debe justificarse y auditarse antes de interpretar el coeficiente como efecto.
    """
    required = {outcome, treated, post}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Faltan columnas: {', '.join(sorted(missing))}")
    frame = data.dropna(subset=list(required)).copy()
    term = f"{treated}:{post}"
    rhs = [treated, post, term] + list(controls or [])
    formula = f"{outcome} ~ " + " + ".join(rhs)
    model = smf.ols(formula, data=frame).fit(cov_type="HC1")
    ci = model.conf_int().loc[term]
    return DifferenceInDifferencesResult(
        treatment_effect=float(model.params[term]),
        standard_error=float(model.bse[term]),
        p_value=float(model.pvalues[term]),
        confidence_low=float(ci.iloc[0]),
        confidence_high=float(ci.iloc[1]),
        n_obs=int(model.nobs),
    )
