import pandas as pd

from replica_cygnus.absorption_history_export.service import _prepare_project_history


def _base_rows():
    return pd.DataFrame([
        {
            "periodo_mes": pd.Timestamp("2026-03-01"),
            "codigo_proyecto": "PX",
            "proyecto": "Proyecto X",
            "tipo_unidad_consolidado": "DEPARTAMENTO",
            "fecha_inicio_comercial": pd.Timestamp("2026-01-15"),
            "primera_fecha_observada": pd.Timestamp("2026-03-01"),
            "ultima_fecha_observada": pd.Timestamp("2026-03-31"),
            "stock_inicio_observado": 0,
            "altas_mes": 10,
            "separaciones_brutas_mes": 2,
            "caidas_mes": 0,
            "movimiento_neto_mes": 2,
            "ventas_minutas_mes": 0,
            "saldo_final_observado": 8,
            "absorcion_bruta_mes": None,
            "absorcion_neta_mes": None,
            "absorcion_neta_6m": None,
        },
        {
            "periodo_mes": pd.Timestamp("2026-04-01"),
            "codigo_proyecto": "PX",
            "proyecto": "Proyecto X",
            "tipo_unidad_consolidado": "DEPARTAMENTO",
            "fecha_inicio_comercial": pd.Timestamp("2026-01-15"),
            "primera_fecha_observada": pd.Timestamp("2026-04-01"),
            "ultima_fecha_observada": pd.Timestamp("2026-04-30"),
            "stock_inicio_observado": 8,
            "altas_mes": 0,
            "separaciones_brutas_mes": 1,
            "caidas_mes": 0,
            "movimiento_neto_mes": 1,
            "ventas_minutas_mes": 1,
            "saldo_final_observado": 7,
            "absorcion_bruta_mes": 0.125,
            "absorcion_neta_mes": 0.125,
            "absorcion_neta_6m": None,
        },
        {
            "periodo_mes": pd.Timestamp("2026-05-01"),
            "codigo_proyecto": "PX",
            "proyecto": "Proyecto X",
            "tipo_unidad_consolidado": "DEPARTAMENTO",
            "fecha_inicio_comercial": pd.Timestamp("2026-01-15"),
            "primera_fecha_observada": pd.Timestamp("2026-05-01"),
            "ultima_fecha_observada": pd.Timestamp("2026-05-31"),
            "stock_inicio_observado": 7,
            "altas_mes": 0,
            "separaciones_brutas_mes": 0,
            "caidas_mes": 0,
            "movimiento_neto_mes": 0,
            "ventas_minutas_mes": 0,
            "saldo_final_observado": 7,
            "absorcion_bruta_mes": 0.0,
            "absorcion_neta_mes": 0.0,
            "absorcion_neta_6m": None,
        },
    ])


def test_history_includes_commercial_months_before_ledger_as_missing_evidence():
    out = _prepare_project_history(_base_rows())
    assert out["periodo_mes"].min() == pd.Timestamp("2026-01-01")
    assert out.loc[out["periodo_mes"] == pd.Timestamp("2026-01-01"), "evidencia_mes"].iat[0] == "SIN_EVIDENCIA_LEDGER"
    assert pd.isna(out.loc[out["periodo_mes"] == pd.Timestamp("2026-01-01"), "stock_inicio_observado"].iat[0])


def test_accumulated_stock_absorption_uses_observed_stock_universe():
    out = _prepare_project_history(_base_rows())
    april = out.loc[out["periodo_mes"] == pd.Timestamp("2026-04-01")].iloc[0]
    assert float(april["stock_ofertado_acumulado"]) == 10.0
    assert float(april["ventas_minutas_acumuladas"]) == 1.0
    assert round(float(april["absorcion_stock_acumulada"]), 6) == 0.3


def test_history_stops_at_last_month_with_observed_stock():
    rows = _base_rows()
    extra = rows.iloc[-1].copy()
    extra["periodo_mes"] = pd.Timestamp("2026-06-01")
    extra["primera_fecha_observada"] = pd.Timestamp("2026-06-01")
    extra["ultima_fecha_observada"] = pd.Timestamp("2026-06-30")
    extra["stock_inicio_observado"] = 0
    extra["saldo_final_observado"] = 0
    extra["altas_mes"] = 0
    extra["separaciones_brutas_mes"] = 0
    extra["caidas_mes"] = 0
    extra["movimiento_neto_mes"] = 0
    extra["ventas_minutas_mes"] = 0
    rows = pd.concat([rows, pd.DataFrame([extra])], ignore_index=True)

    out = _prepare_project_history(rows)
    assert out["periodo_mes"].max() == pd.Timestamp("2026-05-01")
