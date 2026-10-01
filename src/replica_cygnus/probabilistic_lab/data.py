from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class MedallioDatasetAdapter:
    """Lectura SOLO-LECTURA de Medallio; nunca consulta Redshift."""

    project_root: Path
    relation: str = "analytics.int_ciclo_comercial_unidad"

    def load(self) -> pd.DataFrame:
        from replica_cygnus.connections import connect_postgres
        from replica_cygnus.settings import load_settings

        if not self.relation.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Nombre de relación inválido.")

        settings = load_settings(self.project_root, require_source=False)
        conn = connect_postgres(settings)
        try:
            conn.execute("SET TRANSACTION READ ONLY")
            query = f"""
                SELECT
                    codigo_proforma,
                    codigo_unidad,
                    codigo_proyecto,
                    fecha_entrada_stock,
                    fecha_separacion,
                    fecha_venta,
                    primera_fecha_caida,
                    ultima_fecha_caida,
                    cantidad_anulaciones,
                    resultado_ciclo,
                    dias_separacion_venta,
                    dias_separacion_caida,
                    documento_cliente,
                    asesor,
                    tipo_unidad_principal
                FROM {self.relation}
                WHERE fecha_separacion IS NOT NULL
                   OR fecha_venta IS NOT NULL
                   OR primera_fecha_caida IS NOT NULL
            """
            return pd.read_sql_query(query, conn)
        finally:
            conn.rollback()
            conn.close()


class MedallioFeatureBuilder:
    """Transforma el contrato comercial en variables pedagógicas/modelables."""

    DATE_COLUMNS = [
        "fecha_entrada_stock",
        "fecha_separacion",
        "fecha_venta",
        "primera_fecha_caida",
        "ultima_fecha_caida",
    ]

    @classmethod
    def build(cls, df: pd.DataFrame) -> pd.DataFrame:
        x = df.copy()
        for c in cls.DATE_COLUMNS:
            if c in x.columns:
                x[c] = pd.to_datetime(x[c], errors="coerce")

        result = (
            x.get("resultado_ciclo", pd.Series("", index=x.index))
            .fillna("")
            .astype(str)
            .str.lower()
        )

        x["is_sale"] = x["fecha_venta"].notna() | result.str.contains(
            "venta|minuta|vend", regex=True
        )
        x["is_fall"] = (
            x["primera_fecha_caida"].notna()
            | x.get("cantidad_anulaciones", pd.Series(0, index=x.index)).fillna(0).gt(0)
            | result.str.contains("ca[ií]d|anul", regex=True)
        )

        x["days_stock_to_separation"] = (
            x["fecha_separacion"] - x["fecha_entrada_stock"]
        ).dt.days

        sale_days = pd.to_numeric(x.get("dias_separacion_venta"), errors="coerce")
        fall_days = pd.to_numeric(x.get("dias_separacion_caida"), errors="coerce")
        x["days_to_outcome"] = np.where(x["is_sale"], sale_days, fall_days)
        x["days_to_outcome"] = pd.to_numeric(x["days_to_outcome"], errors="coerce")

        sep = x["fecha_separacion"]
        x["separation_year"] = sep.dt.year
        x["separation_month"] = sep.dt.month
        x["separation_weekday"] = sep.dt.weekday
        x["outcome_observed"] = x["is_sale"] | x["is_fall"]

        for c in ["codigo_proyecto", "asesor", "tipo_unidad_principal"]:
            if c in x:
                x[c] = x[c].fillna("SIN_DATO").astype(str)

        return x


class SyntheticDataFactory:
    """Escenarios sintéticos reproducibles con propósito pedagógico."""

    def __init__(self, random_state: int = 42):
        self.rng = np.random.default_rng(random_state)

    def bernoulli_conversion(self, n: int = 1000, p: float = 0.35) -> pd.DataFrame:
        return pd.DataFrame({"converted": self.rng.binomial(1, p, n)})

    def logistic_signal(self, n: int = 1200) -> pd.DataFrame:
        x1 = self.rng.normal(0, 1, n)
        x2 = self.rng.normal(0, 1, n)
        logit = -0.4 + 1.1 * x1 - 0.8 * x2
        p = 1 / (1 + np.exp(-logit))
        y = self.rng.binomial(1, p)
        return pd.DataFrame({"x1": x1, "x2": x2, "p_true": p, "y": y})

    def mixture(self, n: int = 900) -> pd.DataFrame:
        z = self.rng.choice([0, 1, 2], size=n, p=[0.4, 0.35, 0.25])
        means = np.array([[2, 2], [-1, 0], [2, -2]])
        vals = means[z] + self.rng.normal(0, 0.7, size=(n, 2))
        return pd.DataFrame({"x1": vals[:, 0], "x2": vals[:, 1], "latent": z})
