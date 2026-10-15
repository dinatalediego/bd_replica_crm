from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from forecast_evaluation_v28 import (
    capture_current,
    capture_prospective_registry,
    refresh_maturity_v283,
    export_artifacts,
    predictive_status,
)
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


def refresh_predictive_gate_v28(root: Path, cfg: dict, digest: dict, slot: str, dry_run: bool = False):
    """
    Lightweight runtime:
    - freeze current forecasts on every Ambassador run,
    - do NOT perform historical backfill here,
    - read mature performance/gate,
    - export CEO artifacts,
    - feed the Evidence Gate.
    """
    payload = {
        "status": "UNAVAILABLE",
        "gate": {},
        "performance": [],
        "defensible": [],
        "capture": {},
    }

    try:
        settings = load_settings()
        with connect_postgres(settings) as conn:
            # schema may not yet be installed. v2.8.3 can coexist with
            # the legacy v2.8 snapshot layer.
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        to_regclass('model_control.forecast_issue_registry'),
                        to_regclass('model_control.forecast_prediction_snapshot')
                    """
                )
                v283_rel, legacy_rel = cur.fetchone()
                has_v283 = v283_rel is not None
                installed = has_v283 or legacy_rel is not None

            if not installed:
                payload["status"] = "SCHEMA_NOT_INSTALLED"
            else:

                if has_v283:
                    payload["capture"] = capture_prospective_registry(
                        conn,
                        slot=slot,
                        dry_run=dry_run,
                        capture_reason="AMBASSADOR",
                    )
                    if not dry_run:
                        payload["maturity_refresh"] = refresh_maturity_v283(conn)
                    else:
                        payload["maturity_refresh"] = {
                            "status": "DRY_RUN_NOT_MUTATED",
                            "new_matured": 0,
                        }
                else:
                    payload["capture"] = capture_current(conn)

                status = predictive_status(conn)
                payload.update(status)

        if payload.get("status") == "OK":
            export_artifacts(root, payload)

            gate = payload.get("gate") or {}
            mature_wape = gate.get("global_wape_pct")
            mature_bias = gate.get("global_bias_pct")

            # v2.8.3 deliberately clears stale/backtest WAPE until a
            # genuinely issued forecast matures.
            digest.setdefault("summary", {})["forecast_wape_pct"] = (
                float(mature_wape) if mature_wape is not None else None
            )
            digest.setdefault("summary", {})["forecast_bias"] = (
                float(mature_bias) if mature_bias is not None else None
            )

    except Exception as exc:
        payload = {
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gate": {},
            "performance": [],
            "defensible": [],
            "capture": {},
        }

    digest["v28"] = payload
    return digest
