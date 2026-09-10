import pandas as pd

from replica_cygnus.economic_intelligence.features import build_supervised_panel, model_feature_sets
from replica_cygnus.economic_intelligence.models import forecast_stockout_path
from replica_cygnus.economic_intelligence.economics import price_area_indifference_proxy


def _panel():
    return pd.DataFrame({
        "codigo_proyecto": ["P1"] * 4,
        "proyecto": ["Proyecto 1"] * 4,
        "periodo_mes": pd.to_datetime(["2026-01-01","2026-02-01","2026-03-01","2026-04-01"]),
        "movimiento_neto_mes": [2, 3, -1, 4],
        "ventas_minutas_mes": [1, 2, 1, 3],
        "stock_inicio_observado": [20, 18, 15, 16],
        "saldo_final_observado": [18, 15, 16, 12],
        "demanda_neta_market": [2, 3, -1, 4],
        "stock_total_departamentos_actual_ref": [30] * 4,
        "stock_ofertado_observado_acum": [20] * 4,
        "mov_neto_ma3": [2, 2.5, 1.3333, 2.0],
    })


def test_future_targets_are_forward_looking():
    out = build_supervised_panel(_panel(), horizons=(1, 3))
    assert out.loc[0, "target_mov_neto_next_1m"] == 3
    assert out.loc[0, "target_mov_neto_next_3m"] == 6  # 3 + (-1) + 4
    assert pd.isna(out.loc[3, "target_mov_neto_next_1m"])


def test_reference_features_are_separate_from_safe_features():
    sets = model_feature_sets()
    assert "precio_m2_prom_actual_ref" in sets.reference_only
    assert "precio_m2_prom_actual_ref" not in sets.safe_numeric


def test_stockout_path_never_goes_negative():
    path = forecast_stockout_path(10, [3, 4, 5], "2026-09-01")
    assert path.iloc[-1]["stock_fin_pred"] == 0
    assert path["stock_fin_pred"].min() >= 0
    assert path.iloc[-1]["agotado"]


def test_iso_budget_curve_preserves_budget_identity():
    df = price_area_indifference_proxy([50, 100], [500000])
    assert (df["area_m2"] * df["price_m2_iso_budget"]).round(6).eq(500000).all()
