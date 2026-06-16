"""Few-shot example selection module.

Provides embedding-similarity-based selection, MMR diversity selection,
and persistent storage repository for few-shot examples.
"""

from .selector import FewShotSelector
from .diversity import MMRSelector
from .repository import FewShotRepository

__all__ = [
    "FewShotSelector",
    "MMRSelector",
    "FewShotRepository",
]
