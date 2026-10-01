from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import load_lab_config
from .data import MedallioDatasetAdapter, MedallioFeatureBuilder
from .presentation import PresentationBuilder
from .registry import build_families
from .types import FamilyResult, LabContext

LOGGER = logging.getLogger(__name__)


class ProbabilityCourseOrchestrator:
    """Notebook-friendly director for the Medallio probabilistic pipeline."""

    def __init__(
        self,
        project_root: str | Path,
        config_path: str | Path = "configs/probabilistic_lab.yml",
    ):
        self.project_root = Path(project_root).resolve()
        self.config_path = self.project_root / config_path
        self.config = load_lab_config(self.config_path)

        lab_cfg = self.config["lab"]
        self.output_dir = self.project_root / lab_cfg.get(
            "output_dir", "outputs/probabilistic_lab"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_data(self):
        relation = self.config["lab"].get(
            "source_relation", "analytics.int_ciclo_comercial_unidad"
        )
        raw = MedallioDatasetAdapter(self.project_root, relation).load()
        return MedallioFeatureBuilder.build(raw)

    def run_families(self, data) -> list[FamilyResult]:
        families = build_families(self.config.get("families", []))
        ctx = LabContext(
            data=data,
            output_dir=self.output_dir,
            random_state=int(self.config["lab"].get("random_state", 42)),
            config=self.config,
        )
        results = []
        for family in families:
            LOGGER.info("Ejecutando familia %s", family.family_id)
            results.append(family.run(ctx))
        return results

    def save_summary(self, results: list[FamilyResult]) -> Path:
        path = self.output_dir / "experiments" / "summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [result.jsonable() for result in results],
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return path

    def build_pdf(self, results: list[FamilyResult]) -> Path:
        title = self.config["lab"].get(
            "title", "Medallio · Modelos Probabilísticos"
        )
        path = (
            self.output_dir
            / "reports"
            / "medallio_modelos_probabilisticos.pdf"
        )
        return PresentationBuilder(title).build(results, path)

    def run_all(self) -> dict[str, Any]:
        data = self.load_data()
        results = self.run_families(data)
        summary = self.save_summary(results)
        pdf = self.build_pdf(results)
        return {
            "rows": int(len(data)),
            "families": [result.family_id for result in results],
            "summary": str(summary),
            "pdf": str(pdf),
            "results": results,
        }
