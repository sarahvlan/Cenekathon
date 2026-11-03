"""Slice 1: Data Spine & Company Profiling.

Leest ruwe vacatures (Parquet), bepaalt via beursdata de succesvolle, grotere peers van
een doelbedrijf en schrijft de gefilterde vacatures als Contract 1 (`spine_raw_jobs`).
"""

from .config import PipelineConfig
from .pipeline import PipelineResult, TargetNotFoundError, run_pipeline

__all__ = ["PipelineConfig", "PipelineResult", "TargetNotFoundError", "run_pipeline"]
