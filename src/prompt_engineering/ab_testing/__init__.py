"""A/B Testing module for prompt engineering experiments.

Provides deterministic traffic splitting, experiment lifecycle management,
and statistical analysis for comparing prompt template variants.
"""

from .traffic_splitter import TrafficSplitter
from .experiment import ABExperiment, ABResult as ExperimentABResult
from .statistical import ABTestAnalyzer, ABResult as StatisticalABResult

__all__ = [
    "ABExperiment",
    "TrafficSplitter",
    "ABTestAnalyzer",
    "ExperimentABResult",
    "StatisticalABResult",
]
