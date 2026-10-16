from datetime import date
import unittest

from scripts.export_decision_room import build_packet


def history(stock=20, close=17, sales=3, cutoff=date(2026, 10, 15), review=1):
    return [{
        "codigo_proyecto": "MT", "nombre_proyecto": "Matera",
        "periodo_mes": date(2026, 9, 1), "fecha_corte": cutoff,
        "stock_inicial": stock, "ventas_mes": sales, "stock_final": close,
        "unidades_revision": review, "separaciones_brutas": 7,
    }]


def forecast(horizon=1, run="run-2", issued="2026-10-03 12:00:00", origin_stock=17):
    return {
        "project": "MT", "run_id": run, "origin": date(2026, 9, 1),
        "forecast_month": date(2026, 9 + horizon, 1) if horizon <= 3 else date(2027, horizon - 3, 1),
        "horizon": horizon, "model": "mean3", "monthly_prediction": 3.0,
        "prediction": 3.0 * horizon, "lower80": None, "upper80": None,
        "stock_remaining": origin_stock - 3 * horizon,
        "evidence_level": "PROSPECTIVE_AS_ISSUED", "created_at": issued,
    }


def funnel(
    *,
    leads=10,
    unique_clients=8,
    mapped=9,
    ambiguous=0,
    unmatched=1,
    proformas=4,
    separations=7,
    minutas=3,
):
    return {
        "codigo_proyecto": "MT",
        "periodo_mes": date(2026, 9, 1),
        "leads": leads,
        "clientes_unicos": unique_clients,
        "leads_identidad_mapeada": mapped,
        "leads_identidad_ambigua": ambiguous,
        "leads_identidad_sin_match": unmatched,
        "identity_match_rate": mapped / leads if leads else None,
        "proformas": proformas,
        "separaciones": separations,
        "minutas": minutas,
        "commercial_cutoff": date(2026, 10, 16),
        "funnel_semantics": "EVENT_MONTH_NOT_COHORT",
    }


class DecisionRoomExportTests(unittest.TestCase):
    def test_real_packet_preserves_missing_and_source_limitations(self):
        packet = build_packet(history(), [forecast()], "2026-10-16T10:00:00Z")
        project = packet["projects"][0]
        row = project["history"][0]
        self.assertEqual(packet["origin"], "MEDALLIO_LOCAL_AGGREGATE")
        self.assertEqual((row["minutas"], row["separations"]), (3, 7))
        self.assertIsNone(row["leads"])
        self.assertIsNone(row["unique_clients"])
        self.assertIsNone(row["proformas"])
        self.assertIsNone(row["revenue_pen"])
        self.assertIsNone(row["margin_pen"])
        self.assertEqual(project["funnel_meta"]["status"], "UNAVAILABLE")
        self.assertIsNone(project["forecast"][0]["cumulative_lower80"])
        self.assertIn("otro universo", packet["definitions"]["separations"])

    def test_stock_reconciliation_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Stock no concilia"):
            build_packet(history(stock=20, close=18, sales=3), [], "2026-10-16T10:00:00Z")

    def test_latest_run_keeps_all_horizons_even_with_different_issue_timestamps(self):
        old = forecast(run="run-1", issued="2026-10-02 12:00:00")
        current = [forecast(horizon=1), forecast(horizon=2, issued="2026-10-03 12:00:01")]
        packet = build_packet(history(), [old, *current], "2026-10-16T10:00:00Z")
        project = packet["projects"][0]
        self.assertEqual(project["forecast_meta"]["run_id"], "run-2")
        self.assertEqual([row["horizon"] for row in project["forecast"]], [1, 2])

    def test_readiness_ready_only_when_all_four_gates_pass(self):
        rows = history(stock=43, close=40, sales=3, cutoff=date(2026, 10, 16), review=0)
        forecasts = [forecast(horizon=h, origin_stock=40) for h in range(1, 7)]
        packet = build_packet(rows, forecasts, "2026-10-16T15:00:00+00:00")
        readiness = packet["projects"][0]["readiness"]
        self.assertEqual(readiness["status"], "READY")
        self.assertEqual(readiness["failures"], [])
        self.assertTrue(all(gate["status"] == "PASS" for gate in readiness["gates"].values()))
        self.assertEqual(readiness["gates"]["stock_reconciliation"]["delta_units"], 0.0)
        self.assertEqual(packet["readiness_summary"], {"ready_projects": 1, "blocked_projects": 0})

    def test_readiness_blocks_and_explains_every_failed_rule(self):
        rows = history(stock=20, close=17, sales=3, cutoff=date(2026, 10, 15), review=1)
        forecasts = [forecast(horizon=1, origin_stock=18)]
        packet = build_packet(rows, forecasts, "2026-10-16T15:00:00+00:00")
        readiness = packet["projects"][0]["readiness"]
        self.assertEqual(readiness["status"], "BLOCKED")
        self.assertEqual(set(readiness["failures"]), {
            "freshness", "stock_reconciliation", "quality", "forecast_availability",
        })
        self.assertEqual(set(readiness["blocking_reasons"]), {
            "STALE_SOURCE", "STOCK_MISMATCH", "DATA_QUALITY_QUARANTINE", "FORECAST_INCOMPLETE",
        })
        self.assertEqual(readiness["gates"]["stock_reconciliation"]["delta_units"], 1.0)
        self.assertEqual(packet["readiness_summary"], {"ready_projects": 0, "blocked_projects": 1})

    def test_funnel_attaches_activity_without_inventing_cohort_rates(self):
        packet = build_packet(
            history(cutoff=date(2026, 10, 16), review=0),
            [],
            "2026-10-16T15:00:00+00:00",
            funnel_rows=[funnel()],
        )
        project = packet["projects"][0]
        row = project["history"][0]
        self.assertEqual((row["leads"], row["unique_clients"], row["proformas"]), (10, 8, 4))
        self.assertEqual(project["funnel_meta"]["status"], "AVAILABLE")
        self.assertFalse(project["funnel_meta"]["conversion_rates_allowed"])
        self.assertEqual(project["funnel"][0]["lead_identity"]["match_rate"], 0.9)
        self.assertIn("NO es una cohorte", packet["definitions"]["funnel"])

    def test_funnel_rejects_mismatch_with_governed_minutas(self):
        bad = funnel(minutas=2)
        with self.assertRaisesRegex(ValueError, "Funnel/minutas no concilia"):
            build_packet(
                history(cutoff=date(2026, 10, 16), review=0),
                [],
                "2026-10-16T15:00:00+00:00",
                funnel_rows=[bad],
            )


if __name__ == "__main__":
    unittest.main()
