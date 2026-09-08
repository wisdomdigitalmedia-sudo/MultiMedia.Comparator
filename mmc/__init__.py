"""MultiMedia.Comparator — find duplicate media and pick the best copy."""

from __future__ import annotations

__version__ = "1.0.0"

from mmc.integration import CompareResult, compare_catalog, compare_items, score_item
from mmc.quality import QualityScore

__all__ = [
    "__version__",
    "CompareResult",
    "QualityScore",
    "compare_catalog",
    "compare_items",
    "score_item",
]
