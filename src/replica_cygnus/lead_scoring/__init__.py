"""Lead scoring production loop for Medallio.

Los módulos de base de datos se importan de forma explícita para mantener el
paquete liviano y testeable sin abrir conexiones al importar.
"""

from .config import LeadScoringConfig, load_lead_scoring_config
from .feedback import (
    measurement_summary,
    refresh_outcomes,
    register_action,
    sync_recommendations,
)

__all__ = [
    "LeadScoringConfig",
    "load_lead_scoring_config",
    "measurement_summary",
    "refresh_outcomes",
    "register_action",
    "sync_recommendations",
]
