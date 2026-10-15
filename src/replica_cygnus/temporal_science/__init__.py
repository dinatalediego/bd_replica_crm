"""Time-aware forecasting control plane for Medallio.

The package is additive: it profiles governed local datasets, records model
suitability, and coordinates macro/micro forecasting without mutating canonical
commercial facts.
"""

from .profiling import profile_numeric, profile_series, recommend_models

__all__ = ["profile_numeric", "profile_series", "recommend_models"]
