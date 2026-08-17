from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .runtime import score_candidates
from .settings import PostgresSettings
from .store import load_candidates, persist_recommendation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cygnus-decision-engine")
    parser.add_argument("--env-file", default=".env", help="Ruta al .env del repositorio padre.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-separation-risk", help="Genera y persiste recomendaciones para separaciones activas.")
    run.add_argument("--dry-run", action="store_true", help="Evalúa candidatos pero no escribe recomendaciones.")
    run.add_argument("--top", type=int, default=20, help="Número de recomendaciones a imprimir.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    load_dotenv(Path(args.env_file))

    if args.command == "run-separation-risk":
        settings = PostgresSettings.from_env()
        with settings.connect() as conn:
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

            payload = [
                {
                    "recommendation_id": item.recommendation_id,
                    "entity_id": item.entity_id,
                    "action": item.action,
                    "score": item.score,
                    "status": item.status,
                    "explanation": item.explanation,
                }
                for item in recommendations[: max(args.top, 0)]
            ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print(f"candidates={len(candidates)} persisted={0 if args.dry_run else len(recommendations)}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
