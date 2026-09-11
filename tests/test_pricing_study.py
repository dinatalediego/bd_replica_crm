import pandas as pd

from replica_cygnus.pricing_study.service import build_scenarios, classify_unit_actions


def _config():
    return {
        "planning": {
            "scenario_price_deltas": [-0.05, 0.0, 0.05],
            "stress_test_elasticity": -1.0,
            "min_absorption_retention_ratio": 0.80,
        },
        "unit_review_policy": {
            "high_price_index": 1.08,
            "low_price_index": 0.92,
            "slow_stock_months": 6.0,
            "fast_stock_months": 3.0,
            "review_down_delta": -0.025,
            "review_up_delta": 0.025,
        },
    }


def test_build_scenarios_marks_one_recommendation_per_project():
    scorecard = pd.DataFrame(
        [
            {
                "codigo_proyecto": "P1",
                "nombre_proyecto": "Proyecto 1",
                "departamentos_disponibles": 20,
                "stock_fin": 20,
                "precio_lista_promedio_disponible": 300000,
                "absorcion_neta_30d": 0.10,
            },
            {
                "codigo_proyecto": "P2",
                "nombre_proyecto": "Proyecto 2",
                "departamentos_disponibles": 10,
                "stock_fin": 10,
                "precio_lista_promedio_disponible": 450000,
                "absorcion_neta_30d": 0.08,
            },
        ]
    )

    result = build_scenarios(scorecard, _config())

    assert len(result) == 6
    assert result.groupby("proyecto")["recommended_in_stress_test"].sum().eq(1).all()
    assert result["scenario_mode"].eq("STRESS_TEST_NOT_CAUSAL").all()


def test_classify_unit_actions_uses_price_corridor_and_stock_speed():
    units = pd.DataFrame(
        [
            {
                "codigo_proyecto": "P1",
                "nombre_proyecto": "Proyecto 1",
                "codigo_unidad": "101",
                "estado_bucket": "DISPONIBLE",
                "precio_lista": 300000,
                "indice_precio_vs_benchmark_interno": 1.12,
                "area_total": 70,
            },
            {
                "codigo_proyecto": "P2",
                "nombre_proyecto": "Proyecto 2",
                "codigo_unidad": "202",
                "estado_bucket": "DISPONIBLE",
                "precio_lista": 400000,
                "indice_precio_vs_benchmark_interno": 0.88,
                "area_total": 80,
            },
        ]
    )
    scorecard = pd.DataFrame(
        [
            {"codigo_proyecto": "P1", "meses_stock_ventas_30d": 8.0, "absorcion_neta_30d": 0.05},
            {"codigo_proyecto": "P2", "meses_stock_ventas_30d": 2.0, "absorcion_neta_30d": 0.20},
        ]
    )

    result = classify_unit_actions(units, scorecard, _config())
    by_unit = result.set_index("codigo_unidad")

    assert by_unit.loc["101", "accion_revision"] == "REVISAR_DESCUENTO"
    assert by_unit.loc["202", "accion_revision"] == "TEST_SUBIDA"
    assert by_unit["decision_status"].eq("REQUIERE_APROBACION_COMERCIAL").all()
