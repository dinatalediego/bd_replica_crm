from pathlib import Path

import pandas as pd

from replica_cygnus.probabilistic_lab.data import (
    MedallioFeatureBuilder,
    SyntheticDataFactory,
)


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_is_reproducible():
    first = SyntheticDataFactory(42).bernoulli_conversion(100, 0.3)
    second = SyntheticDataFactory(42).bernoulli_conversion(100, 0.3)
    pd.testing.assert_frame_equal(first, second)


def test_feature_builder_does_not_mark_open_cycle_as_observed():
    df = pd.DataFrame(
        {
            "fecha_entrada_stock": ["2026-01-01"],
            "fecha_separacion": ["2026-01-10"],
            "fecha_venta": [None],
            "primera_fecha_caida": [None],
            "ultima_fecha_caida": [None],
            "cantidad_anulaciones": [0],
            "resultado_ciclo": ["SEPARACION"],
            "dias_separacion_venta": [None],
            "dias_separacion_caida": [None],
            "codigo_proyecto": ["P1"],
            "asesor": ["A1"],
            "tipo_unidad_principal": ["departamento flat"],
        }
    )
    out = MedallioFeatureBuilder.build(df)
    assert bool(out.loc[0, "is_sale"]) is False
    assert bool(out.loc[0, "is_fall"]) is False
    assert bool(out.loc[0, "outcome_observed"]) is False


def test_feature_builder_flags_sale_and_duration():
    df = pd.DataFrame(
        {
            "fecha_entrada_stock": ["2026-01-01"],
            "fecha_separacion": ["2026-01-10"],
            "fecha_venta": ["2026-01-20"],
            "primera_fecha_caida": [None],
            "ultima_fecha_caida": [None],
            "cantidad_anulaciones": [0],
            "resultado_ciclo": ["VENTA"],
            "dias_separacion_venta": [10],
            "dias_separacion_caida": [None],
            "codigo_proyecto": ["P1"],
            "asesor": ["A1"],
            "tipo_unidad_principal": ["departamento flat"],
        }
    )
    out = MedallioFeatureBuilder.build(df)
    assert bool(out.loc[0, "is_sale"]) is True
    assert bool(out.loc[0, "outcome_observed"]) is True
    assert int(out.loc[0, "days_stock_to_separation"]) == 9
    assert int(out.loc[0, "days_to_outcome"]) == 10


def test_lab_adapter_never_imports_redshift_connection():
    code = (
        ROOT
        / "src"
        / "replica_cygnus"
        / "probabilistic_lab"
        / "data.py"
    ).read_text(encoding="utf-8")
    assert "connect_redshift" not in code
    assert "SET TRANSACTION READ ONLY" in code
