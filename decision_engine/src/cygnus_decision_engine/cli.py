from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from psycopg.rows import dict_row

from .runtime import score_candidates
from .settings import PostgresSettings
from .store import load_candidates, persist_recommendation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cygnus-decision-engine")
    parser.add_argument("--env-file", default=".env", help="Ruta al .env del repositorio padre.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "install-separation-risk",
        help="Instala control, feature contract y vistas operativas de separation_fall_risk.",
    )
    sub.add_parser(
        "validate-separation-risk",
        help="Valida el feature contract actual antes de generar decisiones.",
    )

    run = sub.add_parser("run-separation-risk", help="Genera y persiste recomendaciones para separaciones activas.")
    run.add_argument("--dry-run", action="store_true", help="Evalúa candidatos pero no escribe recomendaciones.")
    run.add_argument("--top", type=int, default=20, help="Número de recomendaciones a imprimir.")
    return parser


def _decision_engine_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _feature_health(conn) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from features.v_separation_fall_risk_health")
        feature_row = dict(cur.fetchone() or {})

        # CORE owns conversion semantics. fecha_de_minuta is the dated
        # Fecha_PagoCI_pm evidence; pago_ci is a categorical positive marker.
        cur.execute("select * from core.v_ciclo_comercial_health")
        core_row = dict(cur.fetchone() or {})

    required_sale_fields = {
        "abiertas_residenciales_con_pago_ci",
        "ventas_por_pago_ci",
        "ventas_legacy_pre_2026",
        "ventas_post_2026_sin_pago_ci",
        "marcadores_pago_ci_confirmados_sin_fecha",
        "marcadores_pago_ci_desconocidos",
    }
    feature_row.update(
        {
            "core_sale_date_contract_ready": required_sale_fields.issubset(core_row),
            "core_abiertas_residenciales_con_pago_ci": core_row.get(
                "abiertas_residenciales_con_pago_ci"
            ),
            "core_ventas_por_pago_ci": core_row.get("ventas_por_pago_ci"),
            "core_ventas_legacy_pre_2026": core_row.get("ventas_legacy_pre_2026"),
            "core_ventas_post_2026_sin_pago_ci": core_row.get(
                "ventas_post_2026_sin_pago_ci"
            ),
            "core_marcadores_pago_ci_confirmados_sin_fecha": core_row.get(
                "marcadores_pago_ci_confirmados_sin_fecha"
            ),
            "core_marcadores_pago_ci_desconocidos": core_row.get(
                "marcadores_pago_ci_desconocidos"
            ),
        }
    )
    return feature_row


def _separation_risk_health_is_unsafe(health: dict[str, Any]) -> bool:
    """Hard gates for the operational candidate set.

    Normal exclusions (old proformas, active Entrega processes, confirmed
    pago_ci markers, missing source dates) do not poison a safe scoring set if
    they are explicitly accounted for. Any candidate that actually reaches
    scoring with conversion or active-delivery evidence is a hard failure.
    """

    if not bool(health.get("core_sale_date_contract_ready")):
        return True

    hard_count_fields = (
        "duplicate_candidates",
        "quality_blocked",
        "missing_observed_at",
        "current_outside_proforma_recency_window",
        "excluded_proforma_after_observed_at",
        "excluded_missing_observed_at",
        "current_with_pago_ci_marker",
        "current_with_active_entrega_process",
        "core_abiertas_residenciales_con_pago_ci",
        "core_ventas_post_2026_sin_pago_ci",
        "core_marcadores_pago_ci_desconocidos",
    )
    if any(int(health.get(field) or 0) > 0 for field in hard_count_fields):
        return True

    candidates = int(health.get("candidates") or 0)
    eligible = int(health.get("eligible_candidates") or 0)
    distinct = int(health.get("distinct_candidates") or 0)
    if candidates != eligible or candidates != distinct:
        return True

    universe = int(health.get("universe_candidates") or 0)
    accounted_universe = sum(
        int(health.get(field) or 0)
        for field in (
            "eligible_candidates",
            "excluded_active_entrega_process",
            "excluded_proforma_older_than_3_months",
            "excluded_missing_proforma_date",
            "excluded_proforma_after_observed_at",
            "excluded_missing_observed_at",
            "excluded_pago_ci_marker_confirmed",
            "blocked_unknown_pago_ci_marker",
        )
    )
    return universe != accounted_universe


def _install_separation_risk(conn) -> list[str]:
    root = _decision_engine_root()
    sql_files = [
        root / "sql" / "00_decision_control.sql",
        root / "sql" / "02_separation_fall_risk_features.sql",
        root / "sql" / "01_separation_fall_risk_runtime.sql",
    ]

    installed: list[str] = []
    with conn.cursor() as cur:
        for sql_path in sql_files:
            sql_text = sql_path.read_text(encoding="utf-8")
            cur.execute(sql_text, prepare=False)
            installed.append(sql_path.name)
    conn.commit()
    return installed


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    load_dotenv(Path(args.env_file))
    settings = PostgresSettings.from_env()

    if args.command == "install-separation-risk":
        with settings.connect() as conn:
            installed = _install_separation_risk(conn)
            health = _feature_health(conn)
        print(json.dumps({"installed": installed, "feature_health": health}, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "validate-separation-risk":
        with settings.connect() as conn:
            health = _feature_health(conn)
        print(json.dumps(health, ensure_ascii=False, indent=2, default=str))

        if _separation_risk_health_is_unsafe(health):
            print(
                "Gate separation_fall_risk NO aprobado: hay duplicados/leakage, "
                "evidencia de conversión o Entrega Activa dentro del scoring, o el lifecycle "
                "no cumple el contrato fecha_de_minuta/pago_ci-marker."
            )
            return 1

        excluded_old = int(health.get("excluded_proforma_older_than_3_months") or 0)
        excluded_paid_marker = int(health.get("excluded_pago_ci_marker_confirmed") or 0)
        excluded_active_entrega = int(health.get("excluded_active_entrega_process") or 0)
        missing_proforma_date = int(health.get("excluded_missing_proforma_date") or 0)
        sales_by_payment_date = int(health.get("core_ventas_por_pago_ci") or 0)
        marker_without_date = int(
            health.get("core_marcadores_pago_ci_confirmados_sin_fecha") or 0
        )
        print(
            "Gate separation_fall_risk APROBADO: scoring limitado a oportunidades "
            "recientes, sin evidencia de conversión y sin proceso Entrega Activo. "
            f"Excluidas por Entrega Activa={excluded_active_entrega}; "
            f"excluidas por antigüedad={excluded_old}; "
            f"excluidas por marcador pago_ci={excluded_paid_marker}; "
            f"sin fecha de proforma={missing_proforma_date}; "
            f"ventas fechadas por Fecha_PagoCI_pm={sales_by_payment_date}; "
            f"marcadores de pago sin fecha (deuda temporal, fuera del scoring)={marker_without_date}. "
            "WARN conserva limitaciones explícitas de features proxy."
        )
        return 0

    if args.command == "run-separation-risk":
        with settings.connect() as conn:
            health = _feature_health(conn)
            if _separation_risk_health_is_unsafe(health):
                print(json.dumps(health, ensure_ascii=False, indent=2, default=str))
                print(
                    "Run separation_fall_risk BLOQUEADO por quality gate. "
                    "Ejecuta validate-separation-risk después de refrescar lifecycle/CORE."
                )
                return 1

            candidates = load_candidates(conn)
            recommendations = score_candidates(candidates)
            by_id = {candidate.separation_id: candidate for candidate in candidates}

            if not args.dry_run:
                for recommendation in recommendations:
                    candidate = by_id[recommendation.entity_id]
                    persist_recommendation(
                        conn,
                        recommendation,
                        observed_at=candidate.observed_at,
                        quality_status=candidate.quality_status,
                        feature_snapshot=candidate.features,
                    )
                conn.commit()

            payload = []
            for item in recommendations[: max(args.top, 0)]:
                candidate = by_id[item.entity_id]
                features = candidate.features
                payload.append(
                    {
                        "recommendation_id": item.recommendation_id,
                        "entity_id": item.entity_id,
                        "codigo_proforma": features.get("codigo_proforma"),
                        "codigo_unidad": features.get("codigo_unidad"),
                        "codigo_proyecto": features.get("codigo_proyecto"),
                        "asesor": features.get("asesor"),
                        "proforma_first_seen_at": features.get("proforma_first_seen_at"),
                        "proforma_age_days": features.get("proforma_age_days"),
                        "eligibility_rule": features.get("eligibility_rule"),
                        "days_since_separation": features.get("days_since_separation"),
                        "days_since_last_interaction": features.get("days_since_last_interaction"),
                        "interaction_count_14d": features.get("interaction_count_14d"),
                        "pago_ci_marker_confirmado": features.get("pago_ci_marker_confirmado"),
                        "fecha_pago_ci": features.get("fecha_pago_ci"),
                        "has_active_entrega_process": features.get("has_active_entrega_process"),
                        "active_entrega_process_count": features.get("active_entrega_process_count"),
                        "action": item.action,
                        "score": item.score,
                        "status": item.status,
                        "quality_status": candidate.quality_status,
                        "explanation": item.explanation,
                    }
                )

            action_counts = Counter(item.action for item in recommendations if item.status == "ACTIVE")
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            print(
                "summary="
                + json.dumps(
                    {
                        "candidates": len(candidates),
                        "persisted": 0 if args.dry_run else len(recommendations),
                        "active_action_counts": dict(sorted(action_counts.items())),
                    },
                    ensure_ascii=False,
                )
            )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
