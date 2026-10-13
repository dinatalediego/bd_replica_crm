from __future__ import annotations

"""Run aggregate-only data quality gates against Medallio's local PostgreSQL."""

import argparse
import ast
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER_VERSION = "1.0.0"


@dataclass(frozen=True)
class TestResult:
    test_id: str
    status: str
    exception_count: int
    observed: dict[str, Any]
    threshold: dict[str, Any]
    details: str


FORECAST_RELATIONS = (
    "model_control.forecast_issue_registry",
    "analytics.v_forecast_issue_quality_v284",
    "analytics.v_predictive_pre_maturity_readiness_v284",
    "analytics.v_forecast_maturity_clock_v283",
    "analytics.v_forecast_predictive_gate_v283",
)
RISK_RELATIONS = (
    "features.v_separation_fall_training_point_in_time_audit",
    "features.separation_fall_training_point_in_time",
    "features.v_separation_fall_training_point_in_time_health",
)
SALES_RELATIONS = (
    "analytics.comercial_proyecto_mes",
    "analytics.comercial_unidad_mes",
)

RISK_FEATURE_VIEW_COLUMNS = frozenset({
    "separation_id", "codigo_proforma", "codigo_unidad", "codigo_proyecto",
    "documento_cliente", "asesor", "tipo_unidad_principal", "fecha_separacion",
    "snapshot_at", "landmark_day", "days_since_separation",
    "proforma_age_days_at_snapshot", "proforma_age_days_at_separation",
    "snapshot_iso_weekday", "snapshot_month", "target_fall_before_conversion",
    "snapshots_per_separation", "lifecycle_balancing_weight", "feature_scope",
    "interaction_features_certified", "evaluation_contract",
})
RISK_MODEL_PREDICTORS = (
    "days_since_separation",
    "proforma_age_days_at_snapshot",
    "proforma_age_days_at_separation",
    "snapshot_iso_weekday",
    "snapshot_month",
)
RISK_EVALUATION_CONTRACT = "GROUP_SPLIT_BY_SEPARATION_ID_AND_OUT_OF_TIME_REQUIRED"


def feature_column_differences(actual: set[str] | frozenset[str]) -> tuple[list[str], list[str]]:
    """Return missing and unexpected fields relative to the frozen risk feature contract."""
    return sorted(RISK_FEATURE_VIEW_COLUMNS - set(actual)), sorted(set(actual) - RISK_FEATURE_VIEW_COLUMNS)


def forecast_benchmark_status(active: int, benchmarked: int, minimum_pct: float = 90.0) -> tuple[str, int, float | None]:
    pct = (100.0 * benchmarked / active) if active else None
    exceptions = active - benchmarked if active else 0
    status = "FAIL" if not active or pct is None or pct < minimum_pct else "PASS"
    return status, exceptions, pct


def risk_class_support_status(fall_lifecycles: int, conversion_lifecycles: int, minimum_per_class: int = 30) -> str:
    return "PASS" if min(fall_lifecycles, conversion_lifecycles) >= minimum_per_class else "WARN"


def suite_status(results: list[TestResult]) -> str:
    if any(r.status in {"FAIL", "BLOCKED"} for r in results):
        return "BLOCK"
    if any(r.status == "WARN" for r in results):
        return "WARN"
    return "PASS"


def contract_sha256(root: Path, relative_paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in relative_paths:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"MISSING")
        digest.update(b"\0")
    return digest.hexdigest()


def aggregate_signature(evidence: dict[str, Any]) -> str:
    payload = json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_int(value: Any) -> int:
    return int(value or 0)


def _row(cur, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    cur.execute(sql, params)
    result = cur.fetchone()
    if result is None:
        raise RuntimeError("La consulta de control no devolvió una fila.")
    return result


def _rows(cur, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    cur.execute(sql, params)
    return list(cur.fetchall())


def _relation_presence(cur, relations: tuple[str, ...]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for relation in relations:
        if _row(cur, "SELECT to_regclass(%s)", (relation,))[0] is None:
            missing.append(relation)
    return not missing, missing


def _columns(cur, relation: str) -> set[str]:
    schema, table = relation.split(".", 1)
    return {str(r[0]) for r in _rows(
        cur,
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position""",
        (schema, table),
    )}


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _result(test_id: str, status: str, exceptions: int, observed: dict[str, Any],
            threshold: dict[str, Any], details: str) -> TestResult:
    return TestResult(test_id, status, max(0, int(exceptions)), observed, threshold, details)


def _blocked(test_id: str, missing: list[str]) -> TestResult:
    return _result(test_id, "BLOCKED", 0, {"missing_relations": missing}, {},
                   "No se pudo evaluar porque faltan vistas o tablas requeridas.")


def _forecast_suite(cur) -> tuple[list[TestResult], dict[str, Any]]:
    present, missing = _relation_presence(cur, FORECAST_RELATIONS)
    results = [_result(
        "FC_SCHEMA", "PASS" if present else "FAIL", len(missing),
        {"required_relations": len(FORECAST_RELATIONS), "missing_relations": missing}, {},
        "Contratos requeridos presentes." if present else "Faltan relaciones del registro o del gate de maduración.",
    )]
    if not present:
        results.extend(_blocked(t, missing) for t in (
            "FC_ACTIVE", "FC_NEGATIVE", "FC_STOCK_LIMIT", "FC_HORIZON",
            "FC_BENCHMARK", "FC_TRACEABILITY", "FC_MATURITY"
        ))
        return results, {"source_missing": missing}

    (captured, active, negative, above_stock, misaligned, benchmarked,
     untraceable, mature, start, end) = _row(cur, """
        SELECT count(*)::bigint,
               count(*) FILTER (WHERE canonical_active)::bigint,
               count(*) FILTER (WHERE canonical_active AND pre_maturity_quality_status = 'INVALID_NEGATIVE_PREDICTION')::bigint,
               count(*) FILTER (WHERE canonical_active AND pre_maturity_quality_status = 'CHECK_PREDICTION_ABOVE_STOCK')::bigint,
               count(*) FILTER (WHERE canonical_active AND horizon_alignment_ok IS DISTINCT FROM true)::bigint,
               count(*) FILTER (WHERE canonical_active AND has_primary_benchmark)::bigint,
               count(*) FILTER (WHERE canonical_active AND
                   (NOT has_source_run_id OR NOT has_model_name OR NOT has_model_version OR NOT has_data_cutoff))::bigint,
               count(*) FILTER (WHERE canonical_active AND maturity_status = 'EVALUATED')::bigint,
               min(issue_date_lima), max(issue_date_lima)
        FROM analytics.v_forecast_issue_quality_v284
    """)
    captured, active, negative, above_stock, misaligned, benchmarked, untraceable, mature = map(
        _as_int, (captured, active, negative, above_stock, misaligned, benchmarked, untraceable, mature)
    )
    mature_pairs, predictive_wape, predictive_status = _row(cur, """
        SELECT coalesce(max(mature_pairs), 0)::bigint, max(global_wape_pct), max(gate_status)
        FROM analytics.v_forecast_predictive_gate_v283
    """)
    mature_pairs = _as_int(mature_pairs)
    benchmark_status, benchmark_exceptions, benchmark_pct = forecast_benchmark_status(active, benchmarked)
    results.extend([
        _result("FC_ACTIVE", "PASS" if active else "FAIL", 0 if active else 1,
                {"captured": captured, "active": active}, {"active_minimum": 1},
                "Hay forecasts prospectivos activos." if active else "No hay forecasts activos; no existe población que pueda madurar."),
        _result("FC_NEGATIVE", "PASS" if negative == 0 else "FAIL", negative,
                {"negative_predictions": negative}, {"maximum": 0},
                "Predicciones activas no negativas." if negative == 0 else "Hay predicciones negativas activas."),
        _result("FC_STOCK_LIMIT", "WARN" if above_stock else "PASS", above_stock,
                {"predictions_above_stock": above_stock}, {"preferred": 0},
                "Hay predicciones superiores al stock emitido; validar alcance y unidad antes de evaluar." if above_stock else "Ninguna predicción activa supera el stock registrado."),
        _result("FC_HORIZON", "PASS" if misaligned == 0 else "FAIL", misaligned,
                {"misaligned_active": misaligned}, {"maximum": 0},
                "Horizontes alineados." if misaligned == 0 else "Hay forecasts activos con origen, horizonte y objetivo desalineados."),
        _result("FC_BENCHMARK", benchmark_status, benchmark_exceptions,
                {"active": active, "benchmarked": benchmarked, "coverage_pct": benchmark_pct},
                {"minimum_coverage_pct": 90.0},
                "Cobertura de benchmark suficiente." if benchmark_status == "PASS" else "La comparación contra benchmark no cubre al menos 90% de los forecasts activos."),
        _result("FC_TRACEABILITY", "PASS" if untraceable == 0 else "FAIL", untraceable,
                {"untraceable_active": untraceable}, {"maximum": 0},
                "Forecasts activos trazables a fuente, modelo, versión y corte." if untraceable == 0 else "Faltan identificadores necesarios para reproducir forecasts activos."),
        _result("FC_MATURITY", "PASS" if mature_pairs and predictive_wape is not None else "WARN", 0,
                {"evaluated_active_issues": mature, "mature_pairs": mature_pairs,
                 "wape_pct": predictive_wape, "predictive_gate_status": predictive_status},
                {"minimum_mature_pairs": 1, "wape_required_for_metric_available": True},
                "Hay pares maduros y WAPE disponible; el gate predictivo conserva sus propios umbrales." if mature_pairs and predictive_wape is not None else "No hay pares maduros suficientes para medir WAPE: sigue N/A."),
    ])
    evidence = {
        "captured": captured, "eligible": active, "excluded": max(0, captured - active),
        "negative_predictions": negative, "predictions_above_stock": above_stock,
        "misaligned_active": misaligned, "benchmarked_active": benchmarked,
        "untraceable_active": untraceable, "evaluated_active_issues": mature,
        "mature_pairs": mature_pairs, "wape_pct": predictive_wape,
        "window_start": start, "window_end": end,
    }
    return results, evidence


def _risk_suite(cur) -> tuple[list[TestResult], dict[str, Any]]:
    present, missing = _relation_presence(cur, RISK_RELATIONS)
    results = [_result(
        "RISK_SCHEMA", "PASS" if present else "FAIL", len(missing),
        {"required_relations": len(RISK_RELATIONS), "missing_relations": missing}, {},
        "Vistas de auditoría, entrenamiento y health presentes." if present else "Faltan relaciones del dataset point-in-time.",
    )]
    if not present:
        results.extend(_blocked(t, missing) for t in (
            "RISK_ROWS", "RISK_TIME", "RISK_GRAIN", "RISK_FEATURES", "RISK_TARGET",
            "RISK_SPLIT", "RISK_CLASS_SUPPORT", "RISK_EXCLUSIONS"
        ))
        return results, {"source_missing": missing}

    (audit_rows, train_rows, distinct_lifecycles, fall_lifecycles, conversion_lifecycles,
     blocked_missing, blocked_future, oldest, newest) = _row(cur, """
        SELECT
          (SELECT count(*)::bigint FROM features.v_separation_fall_training_point_in_time_audit),
          h.snapshot_rows, h.distinct_lifecycles, h.fall_lifecycles, h.conversion_lifecycles,
          h.blocked_missing_proforma_first_seen, h.blocked_proforma_after_snapshot,
          h.oldest_snapshot_at, h.newest_snapshot_at
        FROM features.v_separation_fall_training_point_in_time_health h
    """)
    audit_rows, train_rows, distinct_lifecycles, fall_lifecycles, conversion_lifecycles = map(
        _as_int, (audit_rows, train_rows, distinct_lifecycles, fall_lifecycles, conversion_lifecycles)
    )
    blocked_missing, blocked_future = _as_int(blocked_missing), _as_int(blocked_future)
    bad_eligible_time = _as_int(_row(cur, """
        SELECT count(*)::bigint
        FROM features.v_separation_fall_training_point_in_time_audit
        WHERE snapshot_eligibility_status = 'ELIGIBLE'
          AND outcome_at::date <= snapshot_at
    """)[0])
    duplicate_grain = _as_int(_row(cur, """
        SELECT count(*)::bigint FROM (
          SELECT separation_id, snapshot_at
          FROM features.separation_fall_training_point_in_time
          GROUP BY separation_id, snapshot_at HAVING count(*) > 1
        ) d
    """)[0])
    missing_columns, unexpected_columns = feature_column_differences(
        _columns(cur, "features.separation_fall_training_point_in_time")
    )
    invalid_target = _as_int(_row(cur, """
        SELECT count(*)::bigint FROM features.separation_fall_training_point_in_time
        WHERE target_fall_before_conversion IS NULL
           OR target_fall_before_conversion NOT IN (0, 1)
    """)[0])
    invalid_split_contract = _as_int(_row(cur, """
        SELECT count(*)::bigint FROM features.separation_fall_training_point_in_time
        WHERE evaluation_contract IS DISTINCT FROM %s
    """, (RISK_EVALUATION_CONTRACT,))[0])
    results.extend([
        _result("RISK_ROWS", "PASS" if train_rows else "FAIL", 0 if train_rows else 1,
                {"eligible_snapshots": train_rows, "lifecycles": distinct_lifecycles}, {"minimum_snapshots": 1},
                "Hay snapshots elegibles." if train_rows else "El conjunto de entrenamiento está vacío."),
        _result("RISK_TIME", "PASS" if bad_eligible_time == 0 else "FAIL", bad_eligible_time,
                {"eligible_outcome_known_at_snapshot": bad_eligible_time}, {"maximum": 0},
                "No se detectan outcomes conocidos al momento del snapshot." if bad_eligible_time == 0 else "Hay labels disponibles antes o en el corte; esto es fuga temporal."),
        _result("RISK_GRAIN", "PASS" if duplicate_grain == 0 else "FAIL", duplicate_grain,
                {"duplicate_lifecycle_snapshot_keys": duplicate_grain}, {"maximum": 0},
                "Grano lifecycle × snapshot único." if duplicate_grain == 0 else "Hay duplicados en el grano lifecycle × snapshot."),
        _result("RISK_FEATURES", "PASS" if not (missing_columns or unexpected_columns) else "FAIL",
                len(missing_columns) + len(unexpected_columns),
                {"missing_columns": missing_columns, "unexpected_columns": unexpected_columns,
                 "model_predictors": list(RISK_MODEL_PREDICTORS)},
                {"contract": "dataset schema allowlist; only model_predictors are predictors"},
                "Esquema dentro de allowlist; IDs y datos de identificación son metadatos, no predictores." if not (missing_columns or unexpected_columns) else "Cambió el contrato de columnas; revisar leakage y aprobación antes de entrenar."),
        _result("RISK_TARGET", "PASS" if invalid_target == 0 else "FAIL", invalid_target,
                {"non_binary_or_null_targets": invalid_target}, {"allowed_values": [0, 1], "maximum_invalid": 0},
                "Target binario y no nulo." if invalid_target == 0 else "Hay targets ausentes o fuera de {0,1}."),
        _result("RISK_SPLIT", "PASS" if invalid_split_contract == 0 else "FAIL", invalid_split_contract,
                {"rows_without_grouped_out_of_time_contract": invalid_split_contract},
                {"required_contract": RISK_EVALUATION_CONTRACT, "maximum": 0},
                "El dataset requiere split agrupado por lifecycle y fuera de tiempo." if invalid_split_contract == 0 else "El contrato de evaluación no exige agrupación por lifecycle y corte fuera de tiempo."),
        _result("RISK_CLASS_SUPPORT", risk_class_support_status(fall_lifecycles, conversion_lifecycles),
                max(0, 30 - min(fall_lifecycles, conversion_lifecycles)),
                {"fall_lifecycles": fall_lifecycles, "conversion_lifecycles": conversion_lifecycles},
                {"minimum_lifecycles_per_class": 30},
                "El soporte por clase alcanza el umbral inicial." if min(fall_lifecycles, conversion_lifecycles) >= 30 else "Soporte bajo por clase: limitarse a análisis exploratorio y aumentar evidencia antes de comparar modelos."),
        _result("RISK_EXCLUSIONS", "WARN" if blocked_missing + blocked_future else "PASS",
                blocked_missing + blocked_future,
                {"missing_proforma_first_seen": blocked_missing, "proforma_after_snapshot": blocked_future},
                {"preferred": 0},
                "Hay casos bloqueados por evidencia temporal faltante o posterior; permanecen fuera del entrenamiento." if blocked_missing + blocked_future else "No hay bloqueos por evidencia de primera aparición de proforma."),
    ])
    evidence = {
        "source_rows": audit_rows, "eligible": train_rows, "excluded": max(0, audit_rows - train_rows),
        "lifecycles": distinct_lifecycles, "fall_lifecycles": fall_lifecycles,
        "conversion_lifecycles": conversion_lifecycles,
        "invalid_targets": invalid_target, "invalid_split_contract_rows": invalid_split_contract,
        "blocked_missing_proforma_first_seen": blocked_missing,
        "blocked_proforma_after_snapshot": blocked_future,
        "window_start": oldest, "window_end": newest,
    }
    return results, evidence


def _sales_suite(cur) -> tuple[list[TestResult], dict[str, Any]]:
    present, missing = _relation_presence(cur, SALES_RELATIONS)
    results = [_result(
        "SALES_SCHEMA", "PASS" if present else "FAIL", len(missing),
        {"required_relations": len(SALES_RELATIONS), "missing_relations": missing}, {},
        "Panel de ventas instalado." if present else "Faltan tablas del panel de ventas mensual.",
    )]
    if not present:
        results.extend(_blocked(t, missing) for t in (
            "SALES_ROWS", "SALES_GRAIN", "SALES_ROLLFORWARD", "SALES_COMPLETE_MONTH", "SALES_REVIEW_UNITS"
        ))
        return results, {"source_missing": missing}

    (total_rows, complete_rows, partial_rows, review_rows, first_month, last_month,
     duplicate_keys, reconciliation_errors) = _row(cur, """
        SELECT
          (SELECT count(*)::bigint FROM analytics.comercial_proyecto_mes),
          (SELECT count(*)::bigint FROM analytics.comercial_proyecto_mes WHERE NOT mes_parcial),
          (SELECT count(*)::bigint FROM analytics.comercial_proyecto_mes WHERE mes_parcial),
          (SELECT count(*)::bigint FROM analytics.comercial_unidad_mes WHERE requiere_revision),
          (SELECT min(periodo_mes) FROM analytics.comercial_proyecto_mes WHERE NOT mes_parcial),
          (SELECT max(periodo_mes) FROM analytics.comercial_proyecto_mes WHERE NOT mes_parcial),
          (SELECT count(*)::bigint FROM (
             SELECT codigo_proyecto, periodo_mes FROM analytics.comercial_proyecto_mes
             GROUP BY codigo_proyecto, periodo_mes HAVING count(*) > 1
           ) d),
          (SELECT count(*)::bigint FROM analytics.comercial_proyecto_mes
           WHERE stock_lanzamiento < 0 OR stock_inicial < 0 OR ventas_mes < 0 OR ventas_acumuladas < 0
              OR stock_final < 0 OR stock_final <> stock_inicial - ventas_mes
              OR ventas_acumuladas <> stock_lanzamiento - stock_final
              OR stock_lanzamiento < stock_inicial OR stock_final > stock_inicial
              OR dias_exposicion < 0)
    """)
    total_rows, complete_rows, partial_rows, review_rows, duplicate_keys, reconciliation_errors = map(
        _as_int, (total_rows, complete_rows, partial_rows, review_rows, duplicate_keys, reconciliation_errors)
    )
    results.extend([
        _result("SALES_ROWS", "PASS" if complete_rows else "FAIL", 0 if complete_rows else 1,
                {"project_month_rows": total_rows, "complete_month_rows": complete_rows}, {"complete_month_minimum": 1},
                "Hay meses completos para evaluar." if complete_rows else "No hay outcomes mensuales completos para evaluación."),
        _result("SALES_GRAIN", "PASS" if duplicate_keys == 0 else "FAIL", duplicate_keys,
                {"duplicate_project_month_keys": duplicate_keys}, {"maximum": 0},
                "Grano proyecto × mes único." if duplicate_keys == 0 else "Hay más de una fila por proyecto y mes."),
        _result("SALES_ROLLFORWARD", "PASS" if reconciliation_errors == 0 else "FAIL", reconciliation_errors,
                {"stock_sales_reconciliation_errors": reconciliation_errors}, {"maximum": 0},
                "Stock, ventas y exposición reconcilian." if reconciliation_errors == 0 else "Stock/ventas no reconcilian en algunas filas mensuales."),
        _result("SALES_COMPLETE_MONTH", "WARN" if partial_rows else "PASS", partial_rows,
                {"complete_rows": complete_rows, "partial_rows": partial_rows},
                {"train_and_score_on": "mes_parcial = false"},
                "El panel separa meses parciales; excluirlos de la etiqueta y del score hasta completar el mes." if partial_rows else "No hay filas de mes parcial en el panel."),
        _result("SALES_REVIEW_UNITS", "WARN" if review_rows else "PASS", review_rows,
                {"unit_month_rows_marked_for_review": review_rows}, {"preferred": 0},
                "Hay unidades marcadas para revisión; reportar análisis de sensibilidad con y sin estos casos." if review_rows else "No hay unidades marcadas para revisión."),
    ])
    evidence = {
        "source_rows": total_rows, "eligible": complete_rows, "excluded": partial_rows,
        "review_unit_month_rows": review_rows, "window_start": first_month, "window_end": last_month,
    }
    return results, evidence


CODE_ASSET_CONTRACTS: dict[str, tuple[str, ...]] = {
    "CODE_FORECAST_PIPELINE": (
        "scripts/commercial_forecasting.py",
        "src/replica_cygnus/commercial_forecasting/core.py",
        "src/replica_cygnus/commercial_forecasting/evaluation.py",
        "tests/test_commercial_forecasting.py",
        "tests/integration/test_commercial_forecasting_postgres.py",
    ),
    "CODE_SALES_PANEL": (
        "sql/99_evolucion_comercial/01_contract.sql",
        "src/replica_cygnus/commercial_forecasting/service.py",
        "tests/integration/test_commercial_forecasting_postgres.py",
    ),
    "CODE_ECONOMETRIC_PIPELINE": (
        "scripts/econometric_datasets.py",
        "src/replica_cygnus/econometric_datasets/service.py",
        "sql/100_econometria/04_evaluation.sql",
        "tests/integration/test_econometric_postgres.py",
    ),
    "CODE_LEAD_TRAINER": (
        "scripts/lead_scoring.py",
        "src/replica_cygnus/lead_scoring/training.py",
        "tests/test_lead_scoring.py",
    ),
    "CODE_RISK_DATASET": (
        "decision_engine/sql/10_point_in_time_training_set.sql",
        "decision_engine/sql/11_training_readiness_audit.sql",
        "decision_engine/tests/test_point_in_time_training_set.py",
        "decision_engine/tests/test_training_readiness_audit.py",
    ),
    "CODE_GATE_TESTS": (
        "tests/test_model_data_quality_gates.py",
        "tests/integration/test_model_data_quality_gates_postgres.py",
    ),
}
RISK_TRAINER_PATHS = (
    "decision_engine/src/cygnus_decision_engine/training.py",
    "decision_engine/tests/test_supervised_training.py",
)


def audit_code_assets(root: Path, paths: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Return missing assets and syntax errors without importing data code."""
    missing: list[str] = []
    syntax_errors: list[str] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
        elif path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            except (OSError, SyntaxError, UnicodeError):
                syntax_errors.append(relative)
    return missing, syntax_errors


def _code_suite(_cur) -> tuple[list[TestResult], dict[str, Any]]:
    runner = ROOT / "scripts/model_data_quality_gates.py"
    root_ready = ROOT.is_dir() and runner.is_file()
    results = [_result(
        "CODE_SCHEMA", "PASS" if root_ready else "FAIL", 0 if root_ready else 1,
        {"repository_root_available": ROOT.is_dir(), "runner_available": runner.is_file()},
        {"required": ["repository root", "scripts/model_data_quality_gates.py"]},
        "Raíz y runner disponibles." if root_ready else "No se encuentra la raíz del repo o el runner.",
    )]
    checked_files = 0
    missing_total = 0
    syntax_total = 0
    for test_id, paths in CODE_ASSET_CONTRACTS.items():
        missing, syntax_errors = audit_code_assets(ROOT, paths)
        checked_files += len(paths)
        missing_total += len(missing)
        syntax_total += len(syntax_errors)
        status = "PASS" if not missing and not syntax_errors else "FAIL"
        results.append(_result(
            test_id, status, len(missing) + len(syntax_errors),
            {"files_expected": len(paths), "missing_files": missing, "syntax_errors": syntax_errors},
            {"missing_files_maximum": 0, "syntax_errors_maximum": 0},
            "Código y pruebas del pipeline presentes y parseables." if status == "PASS" else "Falta código/prueba del pipeline o hay un archivo Python con sintaxis inválida.",
        ))

    missing_trainer, syntax_trainer = audit_code_assets(ROOT, RISK_TRAINER_PATHS)
    trainer_has_fit = False
    trainer_file = ROOT / RISK_TRAINER_PATHS[0]
    if trainer_file.is_file() and not syntax_trainer:
        tree = ast.parse(trainer_file.read_text(encoding="utf-8"), filename=RISK_TRAINER_PATHS[0])
        trainer_has_fit = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and ("train" in node.name.lower() or "fit" in node.name.lower())
            for node in ast.walk(tree)
        )
    trainer_status = "PASS" if not missing_trainer and not syntax_trainer and trainer_has_fit else "WARN"
    results.append(_result(
        "CODE_RISK_TRAINER", trainer_status,
        len(missing_trainer) + len(syntax_trainer) + (0 if trainer_has_fit else 1),
        {"missing_files": missing_trainer, "syntax_errors": syntax_trainer, "fit_or_train_function": trainer_has_fit},
        {"implementation": RISK_TRAINER_PATHS[0], "test": RISK_TRAINER_PATHS[1]},
        "Trainer supervisado de riesgo y su prueba presentes." if trainer_status == "PASS" else "El dataset PIT y el baseline de reglas existen; falta un trainer supervisado específico y su prueba end-to-end.",
    ))
    evidence = {"checked_code_assets": checked_files + 2, "missing_files": missing_total + len(missing_trainer),
                "syntax_errors": syntax_total + len(syntax_trainer), "risk_supervised_trainer": trainer_status}
    return results, evidence


SUITES: dict[str, dict[str, Any]] = {
    "commercial_forecast": {
        "dataset_key": "forecast_issue_registry",
        "source_relation": "analytics.v_forecast_issue_quality_v284",
        "grain": ("project_key", "target_period", "horizon", "issue_id"),
        "target": "target_period_actual_sales",
        "time": "issued_at",
        "contracts": ("sql/103_forecast_predictive_gate/01_predictive_gate.sql", "sql/107_pre_maturity_control/01_pre_maturity_control.sql"),
        "evaluate": _forecast_suite,
    },
    "separation_fall_risk": {
        "dataset_key": "separation_fall_training_point_in_time",
        "source_relation": "features.separation_fall_training_point_in_time",
        "grain": ("separation_id", "snapshot_at"),
        "target": "target_fall_before_conversion",
        "time": "snapshot_at",
        "contracts": ("decision_engine/sql/10_point_in_time_training_set.sql",),
        "evaluate": _risk_suite,
    },
    "project_month_sales": {
        "dataset_key": "comercial_proyecto_mes",
        "source_relation": "analytics.comercial_proyecto_mes",
        "grain": ("codigo_proyecto", "periodo_mes"),
        "target": "ventas_mes",
        "time": "periodo_mes",
        "contracts": ("sql/99_evolucion_comercial/01_contract.sql",),
        "evaluate": _sales_suite,
    },
    "model_code_readiness": {
        "dataset_key": "model_pipeline_code",
        "evaluate": _code_suite,
        "manifest": False,
    },
}

SUITE_TEST_IDS: dict[str, tuple[str, ...]] = {
    "commercial_forecast": ("FC_SCHEMA", "FC_ACTIVE", "FC_NEGATIVE", "FC_STOCK_LIMIT", "FC_HORIZON", "FC_BENCHMARK", "FC_TRACEABILITY", "FC_MATURITY"),
    "separation_fall_risk": ("RISK_SCHEMA", "RISK_ROWS", "RISK_TIME", "RISK_GRAIN", "RISK_FEATURES", "RISK_TARGET", "RISK_SPLIT", "RISK_CLASS_SUPPORT", "RISK_EXCLUSIONS"),
    "project_month_sales": ("SALES_SCHEMA", "SALES_ROWS", "SALES_GRAIN", "SALES_ROLLFORWARD", "SALES_COMPLETE_MONTH", "SALES_REVIEW_UNITS"),
    "model_code_readiness": ("CODE_SCHEMA", "CODE_FORECAST_PIPELINE", "CODE_SALES_PANEL", "CODE_ECONOMETRIC_PIPELINE", "CODE_LEAD_TRAINER", "CODE_RISK_DATASET", "CODE_RISK_TRAINER", "CODE_GATE_TESTS"),
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _write_manifest(cur, run_id: int, suite_key: str, suite: dict[str, Any],
                    results: list[TestResult], evidence: dict[str, Any], root: Path,
                    gate_status: str, revision: str | None) -> None:
    contract_hash = contract_sha256(root, suite["contracts"])
    signature = aggregate_signature(evidence)
    cur.execute("""
        INSERT INTO model_control.training_dataset_manifest (
            run_id, dataset_key, source_relation, grain_columns, target_column,
            observation_time_column, source_row_count, eligible_row_count,
            excluded_row_count, window_start, window_end, contract_sha256,
            aggregate_signature_sha256, gate_status, evidence
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
        ) ON CONFLICT (run_id, dataset_key) DO UPDATE SET
            source_row_count = EXCLUDED.source_row_count,
            eligible_row_count = EXCLUDED.eligible_row_count,
            excluded_row_count = EXCLUDED.excluded_row_count,
            window_start = EXCLUDED.window_start, window_end = EXCLUDED.window_end,
            contract_sha256 = EXCLUDED.contract_sha256,
            aggregate_signature_sha256 = EXCLUDED.aggregate_signature_sha256,
            gate_status = EXCLUDED.gate_status, evidence = EXCLUDED.evidence
    """, (
        run_id, suite["dataset_key"], suite["source_relation"], list(suite["grain"]),
        suite["target"], suite["time"], int(evidence.get("source_rows", evidence.get("captured", 0))),
        int(evidence.get("eligible", 0)), int(evidence.get("excluded", 0)),
        evidence.get("window_start"), evidence.get("window_end"), contract_hash,
        signature, gate_status, _json({"aggregate_only": True, "revision": revision, **evidence}),
    ))


def run_suite(conn, suite_key: str, root: Path = ROOT, revision: str | None = None) -> tuple[int, str, list[TestResult]]:
    suite = SUITES[suite_key]
    revision = revision if revision is not None else _git_revision(root)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO model_control.data_quality_suite_run
                (suite_key, dataset_key, run_status, code_revision, runner_version)
            VALUES (%s, %s, 'RUNNING', %s, %s)
            RETURNING run_id
        """, (suite_key, suite["dataset_key"], revision, RUNNER_VERSION))
        run_id = int(cur.fetchone()[0])

        # Savepoints let a failed diagnostic become visible as a failed test without
        # leaving PostgreSQL's transaction unusable or discarding the other checks.
        savepoint_n = 0
        try:
            results, evidence = suite["evaluate"](cur)
            actual_ids = {item.test_id for item in results}
            expected_ids = set(SUITE_TEST_IDS[suite_key])
            if actual_ids != expected_ids:
                raise RuntimeError("La suite no emitió exactamente el catálogo de pruebas esperado.")
        except Exception as exc:  # An unexpected SQL/contract change is a visible block.
            results = [_result(SUITE_TEST_IDS[suite_key][0], "FAIL", 1,
                               {"runner_error_type": type(exc).__name__}, {},
                               "El runner no pudo evaluar el contrato; revisar error local sin copiar filas de datos.")]
            evidence = {"runner_error_type": type(exc).__name__}
            # A SQL error aborts this transaction; use a fresh transaction and make a
            # compact ERROR run rather than persisting partial checks.
            conn.rollback()
            with conn.cursor() as error_cur:
                error_cur.execute("""
                    INSERT INTO model_control.data_quality_suite_run
                        (suite_key, dataset_key, run_status, code_revision, runner_version, summary, completed_at)
                    VALUES (%s, %s, 'ERROR', %s, %s, %s::jsonb, now()) RETURNING run_id
                """, (suite_key, suite["dataset_key"], revision, RUNNER_VERSION, _json(evidence)))
                run_id = int(error_cur.fetchone()[0])
                # Catalog test exists; use the suite's schema test ID.
                error_cur.execute("""
                    INSERT INTO model_control.data_quality_test_result
                        (run_id, test_id, result_status, exception_count, observed_value, details)
                    VALUES (%s, %s, 'FAIL', 1, %s::jsonb, %s)
                """, (run_id, results[0].test_id, _json(results[0].observed), results[0].details))
                conn.commit()
            return run_id, "ERROR", results

        status = suite_status(results)
        for item in results:
            savepoint_n += 1
            cur.execute(f"SAVEPOINT dq_result_{savepoint_n}")
            cur.execute("""
                INSERT INTO model_control.data_quality_test_result (
                    run_id, test_id, result_status, exception_count,
                    observed_value, threshold_value, details
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            """, (run_id, item.test_id, item.status, item.exception_count,
                  _json(item.observed), _json(item.threshold), item.details))
            cur.execute(f"RELEASE SAVEPOINT dq_result_{savepoint_n}")

        summary = {"test_count": len(results), "failed": sum(r.status == "FAIL" for r in results),
                   "warnings": sum(r.status == "WARN" for r in results),
                   "blocked": sum(r.status == "BLOCKED" for r in results)}
        cur.execute("""
            UPDATE model_control.data_quality_suite_run
            SET completed_at = now(), run_status = %s, summary = %s::jsonb
            WHERE run_id = %s
        """, (status, _json(summary), run_id))
        if suite.get("manifest", True):
            _write_manifest(cur, run_id, suite_key, suite, results, evidence, root, status, revision)
    conn.commit()
    return run_id, status, results


def print_status(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT suite_key, dataset_key, run_id, completed_at,
                   expected_tests, executed_tests, failed_tests, warning_tests,
                   blocked_tests, data_quality_status
            FROM model_control.v_model_data_quality_latest_gate
            ORDER BY suite_key
        """)
        rows = cur.fetchall()
        print("suite | dataset | run | completed | tests expected/executed | fail | warn | blocked | DQ status")
        for row in rows:
            print(f"{row[0]} | {row[1]} | {row[2] or '-'} | {row[3] or '-'} | "
                  f"{row[4]}/{row[5]} | {row[6]} | {row[7]} | {row[8]} | {row[9]}")
        cur.execute("""
            SELECT dataset_key, source_relation, source_row_count, eligible_row_count,
                   excluded_row_count, window_start, window_end, gate_status,
                   contract_sha256, aggregate_signature_sha256
            FROM model_control.training_dataset_manifest m
            WHERE manifest_id = (
                SELECT max(m2.manifest_id) FROM model_control.training_dataset_manifest m2
                WHERE m2.dataset_key = m.dataset_key
            ) ORDER BY dataset_key
        """)
        manifests = cur.fetchall()
        if manifests:
            print("\nlatest manifests (aggregate only):")
            for row in manifests:
                print(f"{row[0]} | source={row[1]} | rows={row[2]} | eligible={row[3]} | excluded={row[4]} | "
                      f"window={row[5]}..{row[6]} | gate={row[7]} | contract={row[8][:12]} | signature={row[9][:12]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controles locales de calidad de datasets Medallio; no exporta filas fuente.")
    parser.add_argument("command", choices=("run", "status"), nargs="?", default="status")
    parser.add_argument("--suite", action="append", choices=tuple(SUITES), help="Suite a ejecutar; se puede repetir.")
    args = parser.parse_args(argv)

    try:
        from replica_cygnus.connections import connect_postgres
        from replica_cygnus.settings import load_settings
    except ImportError as exc:
        raise SystemExit("Instala el paquete local con `python -m pip install -e .` antes de ejecutar este comando.") from exc

    settings = load_settings(require_source=False)
    with connect_postgres(settings) as conn:
        if args.command == "status":
            print_status(conn)
            return 0
        selected = args.suite or list(SUITES)
        failed = False
        for suite_key in selected:
            run_id, status, results = run_suite(conn, suite_key, Path(settings.project_root))
            failed |= status in {"BLOCK", "ERROR"}
            print(f"[MODEL_DQ] suite={suite_key} run={run_id} status={status}")
            for item in results:
                print(f"  {item.test_id}: {item.status} | exceptions={item.exception_count} | {item.details}")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
