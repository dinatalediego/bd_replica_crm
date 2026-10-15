from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from replica_cygnus.temporal_science.micro import fit_micro_horizon
from replica_cygnus.temporal_science.profiling import (
    population_stability_index,
    profile_series,
    recommend_models,
)


def test_profile_detects_intermittent_monthly_demand():
    months = pd.date_range("2024-01-01", periods=24, freq="MS")
    values = [0, 0, 1, 0, 0, 2] * 4
    profile = profile_series(pd.DataFrame({"month": months, "y": values}), date_col="month", value_col="y")
    assert profile["observations"] == 24
    assert profile["missing_periods"] == 0
    assert profile["zero_rate"] > 0.5
    assert profile["demand_pattern"] in {"INTERMITTENT", "LUMPY"}
    recs = {r["model_family"]: r for r in recommend_models(profile)}
    assert recs["croston_sba"]["eligible"] is True
    assert recs["moving_average_3"]["deployment_role"] == "BASELINE"


def test_profile_exposes_calendar_gaps_and_blocks_regular_models():
    months = pd.to_datetime(["2025-01-01", "2025-02-01", "2025-04-01", "2025-05-01", "2025-06-01", "2025-07-01", "2025-08-01", "2025-09-01"])
    profile = profile_series(pd.DataFrame({"month": months, "y": np.arange(len(months))}), date_col="month", value_col="y")
    assert profile["missing_periods"] == 1
    recs = {r["model_family"]: r for r in recommend_models(profile)}
    assert recs["ets"]["eligible"] is False


def test_population_stability_index_reacts_to_shift():
    reference = pd.Series(np.tile(np.arange(10), 10))
    same = pd.Series(np.tile(np.arange(10), 5))
    shifted = pd.Series(np.tile(np.arange(20, 30), 5))
    assert population_stability_index(reference, same) is not None
    assert population_stability_index(reference, same) < 0.05
    assert population_stability_index(reference, shifted) > 0.25


def _micro_fixture() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    dates = pd.date_range("2025-01-01", periods=9, freq="MS")
    for cut in dates:
        for i in range(40):
            score = 0.7 * (i % 2) + 0.15 * (cut.month % 3) + rng.normal(0, 0.25)
            target = int(score > 0.55)
            rows.append({
                "codigo_unidad": f"U-{cut:%Y%m}-{i:03d}",
                "codigo_proyecto": "P1" if i < 20 else "P2",
                "fecha_corte": cut,
                "evidencia": "OBSERVADO",
                "information_cutoff": cut + pd.Timedelta(hours=10),
                "disponible": True,
                "pendiente_venta": True,
                "horizonte_dias": 30,
                "ventana_fin": cut + pd.Timedelta(days=30),
                "maduro": cut < dates[-1],
                "venta_vigente": target if cut < dates[-1] else None,
                "elegible_validacion_prospectiva": cut < dates[-1],
                "tipologia": "T1" if i % 2 else "T2",
                "dormitorios": 1 + (i % 3),
                "moneda": "PEN",
                "estado_construccion": "CONSTRUCCION",
                "area_total": 55 + i % 20,
                "area_relativa": 0.8 + (i % 5) / 10,
                "precio_m2": 6000 + 50 * i,
                "precio_relativo": 0.9 + (i % 4) / 10,
                "mes_vida": cut.month,
                "mes_calendario": cut.month,
                "leads_4w": 30 + cut.month,
                "proformas_4w": 8 + i % 4,
                "interacciones_4w": 20 + i % 7,
                "visitas_4w": 5 + i % 3,
                "calidad": {"requiere_revision": False},
            })
    return pd.DataFrame(rows)


def test_micro_model_uses_temporal_validation_and_scores_latest_cut(tmp_path: Path):
    frame = _micro_fixture()
    fit = fit_micro_horizon(frame, 30, tmp_path)
    assert fit is not None
    assert fit.rows_train >= 60
    assert fit.rows_validation >= 50
    assert fit.train_end < fit.validation_start
    assert len(fit.predictions) == 40
    assert fit.predictions.probability.between(0, 1).all()
    assert fit.evidence_level == "PROSPECTIVE_OBSERVED"
