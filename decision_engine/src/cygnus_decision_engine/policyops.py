from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection


DECISION_KEY = "separation_fall_risk"


def get_policy_status(
    conn: Connection,
    *,
    decision_key: str,
    policy_version: str,
) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select lifecycle_status
            from decision_intelligence.policy_registry
            where decision_key = %s
              and policy_version = %s
            """,
            (decision_key, policy_version),
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


def policy_allows_mode(status: str | None, mode: str) -> bool:
    mode = mode.upper()
    status = (status or "").upper()
    if mode == "DRY_RUN":
        return True
    if mode == "SHADOW":
        return status in {"SHADOW", "ACTIVE"}
    if mode == "LIVE":
        return status == "ACTIVE"
    if mode == "BACKTEST":
        return status in {"DRAFT", "SHADOW", "ACTIVE", "PAUSED", "RETIRED"}
    return False


def start_decision_run(
    conn: Connection,
    *,
    decision_key: str,
    policy_version: str,
    run_mode: str,
    observed_at: datetime | None,
    candidate_count: int,
    quality_snapshot: Mapping[str, Any] | None = None,
    source_snapshot: Mapping[str, Any] | None = None,
    git_sha: str | None = None,
) -> str:
    run_id = str(uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into decision_intelligence.decision_run (
                run_id,
                decision_key,
                policy_version,
                run_mode,
                observed_at,
                run_status,
                candidate_count,
                quality_snapshot,
                source_snapshot,
                git_sha
            )
            values (
                %s::uuid, %s, %s, %s, %s, 'RUNNING', %s,
                %s::jsonb, %s::jsonb, %s
            )
            """,
            (
                run_id,
                decision_key,
                policy_version,
                run_mode.upper(),
                observed_at,
                candidate_count,
                json.dumps(dict(quality_snapshot or {}), default=str),
                json.dumps(dict(source_snapshot or {}), default=str),
                git_sha,
            ),
        )
    return run_id


def finish_decision_run(
    conn: Connection,
    *,
    run_id: str,
    run_status: str,
    recommendation_count: int,
    blocked_count: int,
    action_distribution: Mapping[str, int] | None = None,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            update decision_intelligence.decision_run
            set finished_at = now(),
                run_status = %s,
                recommendation_count = %s,
                blocked_count = %s,
                action_distribution = %s::jsonb,
                error_message = %s
            where run_id = %s::uuid
            """,
            (
                run_status.upper(),
                recommendation_count,
                blocked_count,
                json.dumps(dict(action_distribution or {})),
                error_message,
                run_id,
            ),
        )


def promote_policy(
    conn: Connection,
    *,
    decision_key: str,
    policy_version: str,
    lifecycle_status: str,
    approved_by_business: str | None = None,
    approved_by_technical: str | None = None,
) -> None:
    lifecycle_status = lifecycle_status.upper()
    if lifecycle_status not in {"DRAFT", "SHADOW", "ACTIVE", "PAUSED", "RETIRED"}:
        raise ValueError(f"lifecycle_status no soportado: {lifecycle_status}")

    with conn.cursor() as cur:
        cur.execute(
            """
            update decision_intelligence.policy_registry
            set lifecycle_status = %s,
                approved_by_business = coalesce(%s, approved_by_business),
                approved_by_technical = coalesce(%s, approved_by_technical),
                approved_at = case
                    when %s = 'ACTIVE' then now()
                    else approved_at
                end,
                effective_from = case
                    when %s = 'ACTIVE' then coalesce(effective_from, now())
                    else effective_from
                end,
                retired_at = case
                    when %s = 'RETIRED' then now()
                    else retired_at
                end,
                updated_at = now()
            where decision_key = %s
              and policy_version = %s
            """,
            (
                lifecycle_status,
                approved_by_business,
                approved_by_technical,
                lifecycle_status,
                lifecycle_status,
                lifecycle_status,
                decision_key,
                policy_version,
            ),
        )
        if cur.rowcount != 1:
            raise ValueError(
                f"Policy no registrada: {decision_key}/{policy_version}. "
                "Ejecuta primero install-separation-risk."
            )
