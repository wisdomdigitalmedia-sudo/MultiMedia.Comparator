"""Load MultiMedia.Comparator (sibling project) for the Duplicates page."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
# media-host/ lives inside MultiMedia.Comparator after the merge
COMPARATOR_ROOT = _HERE.parent
if not (COMPARATOR_ROOT / "mmc" / "integration.py").is_file():
    COMPARATOR_ROOT = _HERE.parent / "MultiMedia.Comparator"


def comparator_available() -> bool:
    return (COMPARATOR_ROOT / "mmc" / "integration.py").is_file()


def _ensure_path() -> None:
    root = str(COMPARATOR_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def compare_this_catalog(
    catalog_path: str | Path,
    kind: str | None = None,
    min_copies: int = 2,
):
    if not comparator_available():
        raise RuntimeError(
            f"MultiMedia.Comparator not found at {COMPARATOR_ROOT}. "
            "Run the catalog UI from the repo root, or set MMC_CATALOG_DB."
        )
    _ensure_path()
    from mmc.integration import compare_catalog

    return compare_catalog(catalog_path, kind=kind, min_copies=min_copies)


def group_by_key(result: Any, key: str):
    for g in result.groups:
        if g.key == key:
            return g
    return None
