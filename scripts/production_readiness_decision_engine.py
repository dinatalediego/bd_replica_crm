from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from replica_cygnus.connections import connect_postgres, connect_redshift
from replica_cygnus.settings import load_settings


@dataclass(frozen=True)
class Gate:
    gate: str
    status: str
    value: Any
    expected: str
    detail: str


SOURCE_COUNT_SQL = """
select count(*)
from grupocygnus.datos_extras
"""

SOURCE_KEY_COUNT_SQL = """
select count(*)
from (
    select id, nombre
    from grupocygnus.datos_extras
    group by id, nombre
) x
"""

SOURCE_DUPLICATE_KEY_SQL = """
select count(*)
from (
    select id, nombre
    from grupocygnus.datos_extras
    group by id, nombre
    having count(*) > 1
) x
"""

TARGET_COUNT_SQL = """
select count(*)
from raw_cygnus.datos_extras
"""

TARGET_KEY_COUNT_SQL = """
select count(*)
from (
    select id, nombre
    from raw_cygnus.datos_extras
    group by id, nombre
) x
"""

TARGET_DUPLICATE_KEY_SQL = """
select count(*)
from (
    select id, nombre
    from raw_cygnus.datos_extras
    group by id, nombre
    having count(*) > 1
) x
"""


def _scalar(conn, query: str) -> int:
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
    return int(row[0])


def _dict_row(conn, query: str) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query)
        return dict(cur.fetchone() or {})


def _relation_exists(conn, qualified_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s) is not null", (qualified_name,))
        return bool(cur.fetchone()[0])


def _eq_zero(name: str, value: int, detail: str) -> Gate:
    return Gate(name, "PASS" if value == 0 else "FAIL", value, "0", detail)


def _eq(name: str, value: Any, expected_value: Any, detail: str) -> Gate:
    return Gate(
        name,
        "PASS" if value == expected_value else "FAIL",
        value,
        str(expected_value),
        detail,
    )


def _non_blocking(name: str, value: Any, detail: str) -> Gate:
    return Gate(name, "INFO", value, "informativo", detail)


def build_report() -> tuple[dict[str, Any], list[Gate]]:
    settings = load_settings()
    gates: list[Gate] = []

    source = connect_redshift(settings)
    target = connect_postgres(settings)
    try:
        source_rows = _scalar(source, SOURCE_COUNT_SQL)
        source_keys = _scalar(source, SOURCE_KEY_COUNT_SQL)
        source_duplicates = _scalar(source, SOURCE_DUPLICATE_KEY_SQL)

        target_rows = _scalar(target, TARGET_COUNT_SQL)
        target_keys = _scalar(target, TARGET_KEY_COUNT_SQL)
        target_duplicates = _scalar(target, TARGET_DUPLICATE_KEY_SQL)

        gates.extend(
            [
                _eq_zero(
                    "replica.datos_extras.source_duplicate_id_nombre",
                    source_duplicates,
                    "La llave certificada (id,nombre) debe ser única en Redshift.",
                ),
                _eq_zero(
                    "replica.datos_extras.target_duplicate_id_nombre",
                    target_duplicates,
                    "La réplica local no puede duplicar el grain certificado.",
                ),
                _eq(
                    "replica.datos_extras.row_parity",
                    target_rows,
                    source_rows,
                    "Filas PostgreSQL deben reconciliar con Redshift después del full refresh controlado.",
                ),
                _eq(
                    "replica.datos_extras.key_parity",
                    target_keys,
                    source_keys,
                    "Cantidad de claves (id,nombre) debe reconciliar origen-destino.",
                ),
            ]
        )

        feature_health: dict[str, Any] = {}
        core_health: dict[str, Any] = {}
        if _relation_exists(target, "features.v_separation_fall_risk_health"):
            feature_health = _dict_row(target, "select * from features.v_separation_fall_risk_health")
        else:
            gates.append(
                Gate(
                    "decision.feature_contract_installed",
                    "FAIL",
                    False,
                    "True",
                    "Falta features.v_separation_fall_risk_health.",
                )
            )

        if _relation_exists(target, "core.v_ciclo_comercial_health"):
            core_health = _dict_row(target, "select * from core.v_ciclo_comercial_health")
        else:
            gates.append(
                Gate(
                    "decision.core_contract_installed",
                    "FAIL",
                    False,
                    "True",
                    "Falta core.v_ciclo_comercial_health.",
                )
            )

        if feature_health:
            hard_feature_fields = (
                "duplicate_candidates",
                "quality_blocked",
                "missing_observed_at",
                "current_outside_proforma_recency_window",
                "excluded_proforma_after_observed_at",
                "excluded_missing_observed_at",
                "current_with_pago_ci_marker",
                "current_with_active_entrega_process",
                "current_with_positive_initial_payment_amount",
                "current_with_unparseable_initial_payment_amount",
                "blocked_unparseable_initial_payment_amount",
                "blocked_unknown_pago_ci_marker",
            )
            for field in hard_feature_fields:
                gates.append(
                    _eq_zero(
                        f"decision.feature.{field}",
                        int(feature_health.get(field) or 0),
                        "Hard safety gate del universo que llega al scoring.",
                    )
                )

            candidates = int(feature_health.get("candidates") or 0)
            eligible = int(feature_health.get("eligible_candidates") or 0)
            distinct = int(feature_health.get("distinct_candidates") or 0)
            gates.append(
                _eq(
                    "decision.feature.candidates_equal_eligible",
                    candidates,
                    eligible,
                    "El set actual debe coincidir con el bucket ELIGIBLE.",
                )
            )
            gates.append(
                _eq(
                    "decision.feature.candidates_equal_distinct",
                    candidates,
                    distinct,
                    "No puede existir multiplicación de candidatos por joins.",
                )
            )

            accounted = sum(
                int(feature_health.get(field) or 0)
                for field in (
                    "eligible_candidates",
                    "excluded_active_entrega_process",
                    "excluded_proforma_older_than_3_months",
                    "excluded_missing_proforma_date",
                    "excluded_proforma_after_observed_at",
                    "excluded_missing_observed_at",
                    "excluded_pago_ci_marker_confirmed",
                    "blocked_unknown_pago_ci_marker",
                    "excluded_positive_initial_payment_amount",
                    "blocked_unparseable_initial_payment_amount",
                )
            )
            universe = int(feature_health.get("universe_candidates") or 0)
            gates.append(
                _eq(
                    "decision.feature.universe_reconciliation",
                    accounted,
                    universe,
                    "Todo ciclo debe quedar explicado por exactamente un bucket.",
                )
            )
            gates.append(
                _non_blocking(
                    "decision.feature.candidate_count",
                    candidates,
                    "Tamaño del universo accionable después de exclusiones.",
                )
            )

        if core_health:
            for field in (
                "ciclos_duplicados",
                "unidades_no_resueltas",
                "proyectos_no_resueltos",
                "proyectos_inconsistentes",
                "resultados_no_validos",
                "abiertas_residenciales_con_pago_ci",
                "ventas_post_2026_sin_pago_ci",
                "marcadores_pago_ci_desconocidos",
                "montos_pago_ci_no_parseables",
            ):
                if field in core_health:
                    gates.append(
                        _eq_zero(
                            f"core.{field}",
                            int(core_health.get(field) or 0),
                            "CORE debe ser resoluble y consistente con la semántica de conversión.",
                        )
                    )

        policy_status = None
        if _relation_exists(target, "decision_intelligence.policy_registry"):
            with target.cursor() as cur:
                cur.execute(
                    """
                    select lifecycle_status
                    from decision_intelligence.policy_registry
                    where decision_key = 'separation_fall_risk'
                      and policy_version = 'separation-fall-risk-baseline-v0.1.0'
                    """
                )
                row = cur.fetchone()
                policy_status = str(row[0]) if row else None
            gates.append(
                Gate(
                    "policy.registry_status",
                    "PASS" if policy_status in {"SHADOW", "ACTIVE"} else "FAIL",
                    policy_status,
                    "SHADOW or ACTIVE",
                    "El baseline debe estar registrado; SHADOW es el estado esperado antes de promoción.",
                )
            )
        else:
            gates.append(
                Gate(
                    "policy.registry_installed",
                    "FAIL",
                    False,
                    "True",
                    "Falta instalar el control PolicyOps.",
                )
            )

        scorecard_rows: list[dict[str, Any]] = []
        if _relation_exists(target, "decision_intelligence.v_decision_value_scorecard"):
            with target.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    select *
                    from decision_intelligence.v_decision_value_scorecard
                    where decision_key = 'separation_fall_risk'
                    order by period_month desc
                    limit 12
                    """
                )
                scorecard_rows = [dict(row) for row in cur.fetchall()]

        hard_failures = [gate for gate in gates if gate.status == "FAIL"]
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": "READY_FOR_SHADOW" if not hard_failures else "NOT_READY",
            "live_status": (
                "ELIGIBLE_FOR_REVIEW"
                if not hard_failures and policy_status == "ACTIVE"
                else "NOT_LIVE"
            ),
            "replication": {
                "source_rows": source_rows,
                "target_rows": target_rows,
                "source_id_nombre_keys": source_keys,
                "target_id_nombre_keys": target_keys,
                "source_duplicate_keys": source_duplicates,
                "target_duplicate_keys": target_duplicates,
            },
            "feature_health": feature_health,
            "core_health": core_health,
            "policy_status": policy_status,
            "value_scorecard": scorecard_rows,
            "hard_failures": [asdict(gate) for gate in hard_failures],
        }
        return report, gates
    finally:
        source.close()
        target.close()


def _write_outputs(root: Path, report: dict[str, Any], gates: list[Gate]) -> tuple[Path, Path]:
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / "decision_engine_production_readiness.json"
    csv_path = reports / "decision_engine_production_readiness_gates.csv"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=["gate", "status", "value", "expected", "detail"])
        writer.writeheader()
        writer.writerows(asdict(gate) for gate in gates)

    return json_path, csv_path


def main() -> int:
    settings = load_settings()
    report, gates = build_report()
    json_path, csv_path = _write_outputs(settings.project_root, report, gates)

    print("CYGNUS Decision Engine - Production Readiness")
    print(f"overall_status: {report['overall_status']}")
    print(f"live_status: {report['live_status']}")
    print(f"policy_status: {report['policy_status']}")
    print(f"gates: {len(gates)}")
    print(f"failures: {len(report['hard_failures'])}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")

    for gate in gates:
        if gate.status == "FAIL":
            print(f"FAIL {gate.gate}: value={gate.value} expected={gate.expected}")

    return 0 if report["overall_status"] == "READY_FOR_SHADOW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
