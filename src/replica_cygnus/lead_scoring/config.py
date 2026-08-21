from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class LeadSourceConfig:
    schema: str = "raw_cygnus"
    table: str = "clientes_proyectos"
    id_column: str = "id"
    decision_time_column: str = "fecha_asignacion"
    client_document_column: str = "documento_cliente"
    project_code_column: str = "codigo_proyecto"
    advisor_column_candidates: tuple[str, ...] = (
        "usuario_asignado",
        "usuario",
        "username",
        "asesor",
        "nombres_usuario",
    )
    channel_column_candidates: tuple[str, ...] = ("canal", "canal_origen")
    medium_column_candidates: tuple[str, ...] = ("medio", "medio_origen")


@dataclass(frozen=True)
class PromotionConfig:
    top_fraction: float = 0.20
    min_eval_rows: int = 150
    min_positive_sep: int = 15
    min_positive_minuta: int = 8
    max_auc_drop: float = 0.01
    max_brier_increase: float = 0.01
    max_top_rate_drop: float = 0.01
    min_material_improvement: float = 0.005


@dataclass(frozen=True)
class LeadScoringConfig:
    source: LeadSourceConfig = field(default_factory=LeadSourceConfig)
    sep_horizon_days: int = 14
    minuta_horizon_days: int = 60
    score_window_days: int = 14
    training_min_rows: int = 250
    validation_days: int = 30
    test_days: int = 30
    weight_sep: float = 0.55
    weight_minuta: float = 0.45
    artifact_dir: str = "artifacts/lead_scoring"
    promotion: PromotionConfig = field(default_factory=PromotionConfig)

    def validate(self) -> None:
        if self.sep_horizon_days <= 0 or self.minuta_horizon_days <= 0:
            raise ValueError("Los horizontes deben ser positivos.")
        if self.minuta_horizon_days < self.sep_horizon_days:
            raise ValueError("El horizonte de minuta no puede ser menor al de separación.")
        if self.training_min_rows < 50:
            raise ValueError("training_min_rows debe ser al menos 50.")
        if self.validation_days <= 0 or self.test_days <= 0:
            raise ValueError("validation_days y test_days deben ser positivos.")
        if abs((self.weight_sep + self.weight_minuta) - 1.0) > 1e-9:
            raise ValueError("weight_sep + weight_minuta debe sumar 1.")
        if not 0 < self.promotion.top_fraction < 1:
            raise ValueError("promotion.top_fraction debe estar entre 0 y 1.")


def _tuple(value, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(str(item) for item in value)


def load_lead_scoring_config(path: Path) -> LeadScoringConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    source_raw = raw.get("source", {}) or {}
    promotion_raw = raw.get("promotion", {}) or {}

    source_defaults = LeadSourceConfig()
    source = LeadSourceConfig(
        schema=str(source_raw.get("schema", source_defaults.schema)),
        table=str(source_raw.get("table", source_defaults.table)),
        id_column=str(source_raw.get("id_column", source_defaults.id_column)),
        decision_time_column=str(
            source_raw.get("decision_time_column", source_defaults.decision_time_column)
        ),
        client_document_column=str(
            source_raw.get("client_document_column", source_defaults.client_document_column)
        ),
        project_code_column=str(
            source_raw.get("project_code_column", source_defaults.project_code_column)
        ),
        advisor_column_candidates=_tuple(
            source_raw.get("advisor_column_candidates"),
            source_defaults.advisor_column_candidates,
        ),
        channel_column_candidates=_tuple(
            source_raw.get("channel_column_candidates"),
            source_defaults.channel_column_candidates,
        ),
        medium_column_candidates=_tuple(
            source_raw.get("medium_column_candidates"),
            source_defaults.medium_column_candidates,
        ),
    )

    promotion_defaults = PromotionConfig()
    promotion = PromotionConfig(
        top_fraction=float(
            promotion_raw.get("top_fraction", promotion_defaults.top_fraction)
        ),
        min_eval_rows=int(
            promotion_raw.get("min_eval_rows", promotion_defaults.min_eval_rows)
        ),
        min_positive_sep=int(
            promotion_raw.get("min_positive_sep", promotion_defaults.min_positive_sep)
        ),
        min_positive_minuta=int(
            promotion_raw.get(
                "min_positive_minuta", promotion_defaults.min_positive_minuta
            )
        ),
        max_auc_drop=float(
            promotion_raw.get("max_auc_drop", promotion_defaults.max_auc_drop)
        ),
        max_brier_increase=float(
            promotion_raw.get(
                "max_brier_increase", promotion_defaults.max_brier_increase
            )
        ),
        max_top_rate_drop=float(
            promotion_raw.get(
                "max_top_rate_drop", promotion_defaults.max_top_rate_drop
            )
        ),
        min_material_improvement=float(
            promotion_raw.get(
                "min_material_improvement",
                promotion_defaults.min_material_improvement,
            )
        ),
    )

    defaults = LeadScoringConfig()
    result = LeadScoringConfig(
        source=source,
        sep_horizon_days=int(raw.get("sep_horizon_days", defaults.sep_horizon_days)),
        minuta_horizon_days=int(
            raw.get("minuta_horizon_days", defaults.minuta_horizon_days)
        ),
        score_window_days=int(raw.get("score_window_days", defaults.score_window_days)),
        training_min_rows=int(
            raw.get("training_min_rows", defaults.training_min_rows)
        ),
        validation_days=int(raw.get("validation_days", defaults.validation_days)),
        test_days=int(raw.get("test_days", defaults.test_days)),
        weight_sep=float(raw.get("weight_sep", defaults.weight_sep)),
        weight_minuta=float(raw.get("weight_minuta", defaults.weight_minuta)),
        artifact_dir=str(raw.get("artifact_dir", defaults.artifact_dir)),
        promotion=promotion,
    )
    result.validate()
    return result
