from __future__ import annotations

import csv
import random
from pathlib import Path

from .economics import EconomicPolicy
from .engine import DecisionEngine


def run_demo(output_path: Path, seed: int = 42) -> Path:
    """Ejemplo reproducible: probabilidad + uplift causal -> valor -> acción."""
    rng = random.Random(seed)
    rows = []
    for i in range(1, 51):
        probability = rng.uniform(0.05, 0.85)
        # Uplift heterogéneo sintético: algunas intervenciones ayudan mucho, otras casi nada.
        treatment_effect = rng.uniform(-0.01, 0.12)
        rows.append((f"LEAD-{i:04d}", probability, treatment_effect))

    policy = EconomicPolicy(
        value_if_success=18000.0,
        loss_if_failure=0.0,
        action_cost=35.0,
        treatment_effect=0.0,
        opportunity_cost=10.0,
    )
    engine = DecisionEngine(
        action_name="CONTACTO_PRIORITARIO",
        policy=policy,
        min_incremental_value=100.0,
        max_actions=15,
    )
    scored = engine.rank(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "entity_id",
                "probability",
                "treatment_effect_cate",
                "expected_value_no_action",
                "expected_incremental_value",
                "expected_value_with_action",
                "recommended_action",
                "priority_rank",
            ]
        )
        for item in scored:
            writer.writerow(
                [
                    item.entity_id,
                    round(item.probability, 6),
                    round(item.treatment_effect, 6),
                    round(item.expected_value_no_action, 2),
                    round(item.expected_incremental_value, 2),
                    round(item.expected_value_with_action, 2),
                    item.recommended_action,
                    item.priority_rank,
                ]
            )
    return output_path
