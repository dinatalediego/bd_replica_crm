from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from scripts.model_data_quality_gates import (
    ROOT,
    RISK_MODEL_PREDICTORS,
    SUITE_TEST_IDS,
    TestResult as GateResult,
    aggregate_signature,
    audit_code_assets,
    feature_column_differences,
    forecast_benchmark_status,
    risk_class_support_status,
    suite_status,
)


class ModelDataQualityGateTests(unittest.TestCase):
    def test_catalog_and_runner_test_ids_match(self) -> None:
        sql = (ROOT / "sql/115_model_data_quality_gates/01_contract.sql").read_text(encoding="utf-8")
        catalog_ids = set(re.findall(r"\('((?:FC|RISK|SALES|CODE)_[A-Z_]+)'\s*,", sql))
        runner_ids = {test_id for test_ids in SUITE_TEST_IDS.values() for test_id in test_ids}

        self.assertEqual(catalog_ids, runner_ids)

    def test_benchmark_coverage_requires_ninety_percent(self) -> None:
        self.assertEqual(forecast_benchmark_status(10, 9), ("PASS", 1, 90.0))
        status, exceptions, pct = forecast_benchmark_status(100, 89)
        self.assertEqual(status, "FAIL")
        self.assertEqual(exceptions, 11)
        self.assertEqual(pct, 89.0)
        self.assertEqual(forecast_benchmark_status(0, 0)[0], "FAIL")

    def test_risk_feature_allowlist_detects_post_outcome_column(self) -> None:
        columns = {"snapshot_at", "target_fall_before_conversion", "days_since_separation"}
        missing, unexpected = feature_column_differences(columns)
        self.assertIn("lifecycle_balancing_weight", missing)
        self.assertEqual(unexpected, [])
        _, unexpected = feature_column_differences(columns | {"outcome_at"})
        self.assertEqual(unexpected, ["outcome_at"])
        self.assertEqual(len(RISK_MODEL_PREDICTORS), 5)
        self.assertNotIn("documento_cliente", RISK_MODEL_PREDICTORS)
        self.assertNotIn("asesor", RISK_MODEL_PREDICTORS)

    def test_risk_class_support_is_warning_below_thirty_lifecycles(self) -> None:
        self.assertEqual(risk_class_support_status(30, 30), "PASS")
        self.assertEqual(risk_class_support_status(29, 60), "WARN")

    def test_suite_status_never_calls_warning_a_pass(self) -> None:
        self.assertEqual(suite_status([GateResult("A", "PASS", 0, {}, {}, "ok")]), "PASS")
        self.assertEqual(suite_status([GateResult("A", "WARN", 0, {}, {}, "watch")]), "WARN")
        self.assertEqual(suite_status([GateResult("A", "BLOCKED", 0, {}, {}, "missing")]), "BLOCK")

    def test_manifest_signature_is_stable_for_same_aggregate_evidence(self) -> None:
        evidence = {"rows": 20, "excluded": 3, "window_start": "2025-01-01"}
        self.assertEqual(aggregate_signature(evidence), aggregate_signature(dict(reversed(list(evidence.items())))))

    def test_code_audit_reports_missing_files_and_parses_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "trainer.py").write_text("def train():\n    return 1\n", encoding="utf-8")
            missing, syntax_errors = audit_code_assets(root, ("trainer.py", "tests/test_trainer.py"))
            self.assertEqual(missing, ["tests/test_trainer.py"])
            self.assertEqual(syntax_errors, [])


if __name__ == "__main__":
    unittest.main()
