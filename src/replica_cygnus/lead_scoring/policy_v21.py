from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd

from .feedback import recommended_action_for_band

DECISION_SYSTEM = "priorizacion_leads"
POLICY_ID = "lead_priority_v2_1"
POLICY_VERSION = "2.1"
EXPERIMENT_NAME = "lead_priority_v21_pilot"

EXPERIMENT_NAMESPACE = uuid.UUID("c3e337c1-27d4-4a84-95e1-e7015f1723d7")
RUN_NAMESPACE = uuid.UUID("6fb75e60-26e0-42ca-9d5e-3e95f3114df8")
RECOMMENDATION_NAMESPACE = uuid.UUID("b1e2c165-9184-4efc-9cb7-34b115284cde")


@dataclass(frozen=True)
class PolicyRunConfig:
    run_key: str = "pilot_01"
    cohort_size: int = 100
    treatment_share: float = 0.80
    selection_window_days: int = 7
    allowed_bands: tuple[str, ...] = ("A", "B")
    recommendation_ttl_hours: int = 24
    require_full_cohort: bool = True

    @property
    def treatment_target_n(self) -> int:
        return round(self.cohort_size * self.treatment_share)

    @property
    def control_target_n(self) -> int:
        return self.cohort_size - self.treatment_target_n

    def validate(self) -> None:
        if not self.run_key.strip():
            raise ValueError("run_key is required")
        if self.cohort_size <= 1:
            raise ValueError("cohort_size must be > 1")
        if not 0 < self.treatment_share < 1:
            raise ValueError("treatment_share must be between 0 and 1")
        if self.selection_window_days <= 0:
            raise ValueError("selection_window_days must be > 0")
        if not self.allowed_bands:
            raise ValueError("allowed_bands cannot be empty")


def experiment_id() -> str:
    return str(uuid.uuid5(EXPERIMENT_NAMESPACE, f"{DECISION_SYSTEM}:{POLICY_ID}:{EXPERIMENT_NAME}"))


def policy_run_id(run_key: str) -> str:
    return str(uuid.uuid5(RUN_NAMESPACE, f"{experiment_id()}:{run_key}"))


def recommendation_id(run_id: str, score_id: str) -> str:
    return str(uuid.uuid5(RECOMMENDATION_NAMESPACE, f"{run_id}:{score_id}"))


def _stable_hash(run_id: str, entity_id: str) -> str:
    return hashlib.sha256(f"{run_id}:{entity_id}".encode("utf-8")).hexdigest()


def _sql_df(conn, sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        names = [item.name for item in cur.description or []]
        return pd.DataFrame(cur.fetchall(), columns=names)


def ensure_experiment(conn, cfg: PolicyRunConfig) -> str:
    cfg.validate()
    exp_id = experiment_id()
    design = {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "run_contract": "FROZEN_COHORT_EXACT_ALLOCATION_NO_REENTRY",
        "treatment_share": cfg.treatment_share,
        "pilot_capacity": cfg.cohort_size,
        "selection_window_days": cfg.selection_window_days,
        "allowed_bands": list(cfg.allowed_bands),
        "semantics": "PROPENSITY_POLICY_PILOT",
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO experiments.experiments
              (experiment_id,decision_system,experiment_name,hypothesis,
               treatment_description,primary_outcome,causal_estimand,
               started_at,status,design_json)
            VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,now(),'RUNNING',%s::jsonb)
            ON CONFLICT (experiment_id) DO NOTHING
            """,
            (
                exp_id,
                DECISION_SYSTEM,
                EXPERIMENT_NAME,
                "Prioritized commercial attention improves minuta_60d versus business-as-usual.",
                "Treatment receives prioritized recommendation; Control remains business-as-usual.",
                "minuta_60d",
                "ITT: E[Y|assignment=treatment] - E[Y|assignment=control]",
                json.dumps(design, ensure_ascii=False),
            ),
        )
    conn.commit()
    return exp_id


def run_status(conn, run_id: str) -> pd.DataFrame:
    return _sql_df(
        conn,
        "SELECT * FROM experiments.v_policy_run_status WHERE policy_run_id=%s::uuid",
        (run_id,),
    )


def frozen_assignments(conn, run_id: str) -> pd.DataFrame:
    return _sql_df(
        conn,
        """
        SELECT *
        FROM analytics.v_pbi_policy_run_assignments
        WHERE policy_run_id=%s
        ORDER BY policy_rank
        """,
        (run_id,),
    )


def candidate_universe(conn, cfg: PolicyRunConfig) -> pd.DataFrame:
    bands = list(cfg.allowed_bands)
    return _sql_df(
        conn,
        """
        WITH serving AS (
          SELECT DISTINCT ON (s.evidence_key)
            s.score_id::text,
            s.evidence_key,
            s.lead_id,
            s.decision_at,
            s.scored_at,
            s.model_run_id::text,
            s.p_separacion_14d,
            s.p_minuta_60d,
            s.priority_score,
            s.priority_rank,
            s.priority_band,
            e.codigo_proyecto,
            e.asesor,
            e.canal,
            e.medio,
            e.evidence_source,
            e.label_status
          FROM decision_intelligence.lead_scores s
          JOIN features.lead_evidence e USING (evidence_key)
          JOIN model_control.model_runs mr ON mr.model_run_id=s.model_run_id
          JOIN model_control.model_aliases a
            ON a.model_run_id=s.model_run_id
           AND a.decision_system=mr.decision_system
           AND a.model_name=mr.model_name
           AND a.alias_name='serving'
          WHERE mr.decision_system=%s
          ORDER BY s.evidence_key,s.scored_at DESC
        )
        SELECT s.*
        FROM serving s
        WHERE s.evidence_source='LIVE'
          AND s.label_status='PENDING'
          AND s.priority_band = ANY(%s)
          AND s.decision_at >= CURRENT_TIMESTAMP - (%s * interval '1 day')
          -- No re-entry from any governed prior run for this decision system.
          AND NOT EXISTS (
            SELECT 1
            FROM experiments.policy_run_assignments pra
            JOIN experiments.policy_runs pr USING (policy_run_id)
            WHERE pr.decision_system=%s
              AND pra.entity_id=s.evidence_key
          )
          -- No re-entry from pre-V2.1 experiment assignments.
          AND NOT EXISTS (
            SELECT 1
            FROM experiments.assignments ea
            JOIN experiments.experiments ex USING (experiment_id)
            WHERE ex.decision_system=%s
              AND ea.entity_id=s.evidence_key
          )
          -- V2 recommendations are treated as prior policy exposure even if no action exists.
          AND NOT EXISTS (
            SELECT 1
            FROM decision_intelligence.recommendations r
            WHERE r.decision_system=%s
              AND r.entity_id=s.evidence_key
              AND COALESCE(r.context_json->>'policy_id','') IN ('lead_priority_v2','lead_priority_v2_1')
          )
        """,
        (
            DECISION_SYSTEM,
            bands,
            cfg.selection_window_days,
            DECISION_SYSTEM,
            DECISION_SYSTEM,
            DECISION_SYSTEM,
        ),
    )


def preview_cohort(conn, cfg: PolicyRunConfig) -> pd.DataFrame:
    cfg.validate()
    run_id = policy_run_id(cfg.run_key)
    existing = run_status(conn, run_id)
    if len(existing) and existing.iloc[0]["status"] in {"FROZEN", "ACTIVE", "COMPLETED"}:
        return frozen_assignments(conn, run_id)

    frame = candidate_universe(conn, cfg).copy()
    if cfg.require_full_cohort and len(frame) < cfg.cohort_size:
        raise RuntimeError(f"Only {len(frame)} eligible leads for required cohort_size={cfg.cohort_size}")

    band_order = {"A": 1, "B": 2, "C": 3, "D": 4}
    frame["band_order"] = frame["priority_band"].map(band_order)
    selected = (
        frame.sort_values(
            ["band_order", "priority_score", "decision_at", "evidence_key"],
            ascending=[True, False, False, True],
        )
        .head(cfg.cohort_size)
        .copy()
        .reset_index(drop=True)
    )
    selected["policy_rank"] = range(1, len(selected) + 1)
    selected["allocation_hash"] = selected["evidence_key"].astype(str).map(lambda x: _stable_hash(run_id, x))
    allocation = selected.sort_values(["allocation_hash", "evidence_key"]).copy()
    allocation["assignment_order"] = range(1, len(allocation) + 1)
    allocation["treatment_group"] = "CONTROL"
    allocation.loc[allocation["assignment_order"] <= cfg.treatment_target_n, "treatment_group"] = "TREATMENT"
    selected = selected.merge(
        allocation[["evidence_key", "assignment_order", "treatment_group"]],
        on="evidence_key",
        how="left",
    )
    selected["policy_run_id"] = run_id
    selected["experiment_id"] = experiment_id()
    selected["policy_id"] = POLICY_ID
    selected["policy_version"] = POLICY_VERSION
    selected["action_owner_proposed"] = selected["asesor"].fillna("SUPERVISOR_COMERCIAL").replace("", "SUPERVISOR_COMERCIAL")
    return selected


def freeze_cohort(conn, cfg: PolicyRunConfig) -> dict[str, Any]:
    cfg.validate()
    exp_id = ensure_experiment(conn, cfg)
    run_id = policy_run_id(cfg.run_key)
    existing = run_status(conn, run_id)
    if len(existing) and existing.iloc[0]["status"] in {"FROZEN", "ACTIVE", "COMPLETED"}:
        return {"status": "ALREADY_FROZEN", "policy_run_id": run_id, "rows": int(existing.iloc[0]["cohort_n"])}

    cohort = preview_cohort(conn, cfg)
    if len(cohort) != cfg.cohort_size:
        raise RuntimeError(f"Selected {len(cohort)} rows; expected exactly {cfg.cohort_size}")

    selection_as_of = datetime.now(timezone.utc)
    config_json = {
        "allowed_bands": list(cfg.allowed_bands),
        "recommendation_ttl_hours": cfg.recommendation_ttl_hours,
        "legacy_v2_exposure_excluded": True,
        "no_control_reentry": True,
        "selection_order": ["band", "priority_score_desc", "decision_at_desc", "evidence_key"],
    }

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO experiments.policy_runs
                  (policy_run_id,experiment_id,decision_system,policy_id,policy_version,
                   run_key,run_type,status,cohort_size,treatment_target_n,control_target_n,
                   treatment_share,selection_window_days,allocation_method,allocation_seed,
                   selection_as_of,config_json)
                VALUES
                  (%s::uuid,%s::uuid,%s,%s,%s,%s,'PILOT_COHORT','ALLOCATING',%s,%s,%s,%s,%s,
                   'DETERMINISTIC_HASH_EXACT',%s,%s,%s::jsonb)
                ON CONFLICT (policy_run_id) DO NOTHING
                """,
                (
                    run_id, exp_id, DECISION_SYSTEM, POLICY_ID, POLICY_VERSION, cfg.run_key,
                    cfg.cohort_size, cfg.treatment_target_n, cfg.control_target_n,
                    cfg.treatment_share, cfg.selection_window_days, run_id,
                    selection_as_of, json.dumps(config_json, ensure_ascii=False),
                ),
            )

            assignment_rows = []
            legacy_rows = []
            for r in cohort.itertuples():
                assignment_rows.append((
                    run_id, exp_id, str(r.evidence_key), str(r.score_id), str(r.model_run_id),
                    int(r.policy_rank), int(r.assignment_order), str(r.treatment_group),
                    str(r.priority_band), float(r.priority_score), float(r.p_separacion_14d),
                    float(r.p_minuta_60d), r.decision_at, r.codigo_proyecto, r.asesor,
                    r.canal, r.medio, r.action_owner_proposed,
                    json.dumps({"policy_id": POLICY_ID, "policy_version": POLICY_VERSION, "run_key": cfg.run_key}, ensure_ascii=False),
                ))
                legacy_rows.append((exp_id, str(r.evidence_key), str(r.treatment_group)))

            cur.executemany(
                """
                INSERT INTO experiments.policy_run_assignments
                  (policy_run_id,experiment_id,entity_id,score_id,model_run_id,policy_rank,
                   assignment_order,treatment_group,priority_band,priority_score,
                   p_separacion_14d,p_minuta_60d,decision_at,codigo_proyecto,asesor,canal,medio,
                   action_owner_proposed,context_json)
                VALUES
                  (%s::uuid,%s::uuid,%s,%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                """,
                assignment_rows,
            )
            cur.executemany(
                """
                INSERT INTO experiments.assignments
                  (experiment_id,entity_id,treatment_group,assigned_at)
                VALUES (%s::uuid,%s,%s,now())
                ON CONFLICT (experiment_id,entity_id) DO NOTHING
                """,
                legacy_rows,
            )
            cur.execute("SELECT * FROM experiments.freeze_policy_run(%s::uuid)", (run_id,))
            freeze_result = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "status": freeze_result[1],
        "policy_run_id": run_id,
        "cohort_n": int(freeze_result[2]),
        "treatment_n": int(freeze_result[3]),
        "control_n": int(freeze_result[4]),
        "frozen_at": freeze_result[5],
    }


def materialize_recommendations(conn, cfg: PolicyRunConfig) -> dict[str, Any]:
    run_id = policy_run_id(cfg.run_key)
    status = run_status(conn, run_id)
    if status.empty or status.iloc[0]["status"] not in {"FROZEN", "ACTIVE"}:
        raise RuntimeError("Run must be FROZEN or ACTIVE before recommendations are materialized")
    if not bool(status.iloc[0]["exact_allocation_ok"]):
        raise RuntimeError("Exact allocation gate failed")
    if not bool(status.iloc[0]["control_clean"]):
        raise RuntimeError("Control contamination detected")

    rows = _sql_df(
        conn,
        """
        SELECT
          a.*, s.score_id::text, s.model_run_id::text, s.scored_at,
          e.lead_id
        FROM experiments.policy_run_assignments a
        JOIN decision_intelligence.lead_scores s ON s.score_id=a.score_id
        JOIN features.lead_evidence e ON e.evidence_key=a.entity_id
        WHERE a.policy_run_id=%s::uuid
          AND a.treatment_group='TREATMENT'
        ORDER BY a.policy_rank
        """,
        (run_id,),
    )

    recommended_at = datetime.now(timezone.utc)
    expires_at = recommended_at + timedelta(hours=cfg.recommendation_ttl_hours)
    records = []
    for r in rows.itertuples():
        rec_id = recommendation_id(run_id, str(r.score_id))
        context = {
            "semantics": "PROPENSITY_NOT_CAUSAL_UPLIFT",
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "policy_run_id": run_id,
            "policy_run_key": cfg.run_key,
            "experiment_id": experiment_id(),
            "treatment_group": "TREATMENT",
            "score_id": str(r.score_id),
            "evidence_key": str(r.entity_id),
            "lead_id": str(r.lead_id),
            "policy_rank": int(r.policy_rank),
            "assignment_order": int(r.assignment_order),
            "priority_band": str(r.priority_band),
            "priority_score": float(r.priority_score),
            "p_separacion_14d": float(r.p_separacion_14d),
            "p_minuta_60d": float(r.p_minuta_60d),
            "codigo_proyecto": r.codigo_proyecto,
            "asesor": r.asesor,
            "canal": r.canal,
            "medio": r.medio,
            "action_owner_proposed": r.action_owner_proposed,
            "sla_minutes": 15 if r.priority_band == "A" else 60,
            "recommended_at": recommended_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        records.append((
            rec_id, DECISION_SYSTEM, str(r.entity_id), recommended_at, str(r.model_run_id),
            float(r.p_minuta_60d), recommended_action_for_band(str(r.priority_band)),
            int(r.policy_rank), json.dumps(context, ensure_ascii=False),
        ))

    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO decision_intelligence.recommendations
                  (recommendation_id,decision_system,entity_id,scored_at,model_run_id,
                   predicted_probability,recommended_action,priority_rank,context_json)
                VALUES (%s::uuid,%s,%s,%s,%s::uuid,%s,%s,%s,%s::jsonb)
                ON CONFLICT (recommendation_id) DO UPDATE SET
                  predicted_probability=EXCLUDED.predicted_probability,
                  recommended_action=EXCLUDED.recommended_action,
                  priority_rank=EXCLUDED.priority_rank,
                  context_json=EXCLUDED.context_json
                """,
                records,
            )
            # Hard contamination check before activation.
            cur.execute(
                """
                SELECT COUNT(*)
                FROM decision_intelligence.recommendations r
                WHERE r.decision_system=%s
                  AND r.context_json->>'policy_run_id'=%s
                  AND r.context_json->>'treatment_group'='CONTROL'
                """,
                (DECISION_SYSTEM, run_id),
            )
            if cur.fetchone()[0] != 0:
                raise RuntimeError("Control recommendation contamination detected")
            cur.execute(
                """
                UPDATE experiments.policy_runs
                SET status='ACTIVE', activated_at=COALESCE(activated_at,now()), updated_at=now()
                WHERE policy_run_id=%s::uuid AND status='FROZEN'
                """,
                (run_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {"policy_run_id": run_id, "recommendations": len(records), "status": "ACTIVE"}
