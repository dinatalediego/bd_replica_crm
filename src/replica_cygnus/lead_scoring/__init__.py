"""Lead scoring production loop for Medallio.

Los módulos de base de datos se importan de forma explícita para mantener el
paquete liviano y testeable sin abrir conexiones al importar.
"""

from .config import LeadScoringConfig, load_lead_scoring_config

__all__ = ["LeadScoringConfig", "load_lead_scoring_config"]
