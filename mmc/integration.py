"""Public API for Entertainment.Servers (and the standalone app)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mmc.catalog_import import load_catalog_items
from mmc.grouper import DuplicateGroup, group_items, groups_to_jsonable
from mmc.probe import ProbeResult
from mmc.quality import QualityScore
from mmc.quality import score_item as score_media


@dataclass
class CompareResult:
    groups: list[DuplicateGroup]
    item_count: int
    group_count: int
    extra_copies: int
    catalog_path: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        extras = sum(max(0, len(g.copies) - 1) for g in self.groups)
        return {
            "item_count": self.item_count,
            "group_count": len(self.groups),
            "extra_copies": extras,
            "catalog_path": self.catalog_path,
            "notes": self.notes,
            "groups": groups_to_jsonable(self.groups),
        }


def compare_items(
    items: list[dict[str, Any]],
    probes: dict[str, ProbeResult] | None = None,
    min_copies: int = 2,
    kind: str | None = None,
) -> CompareResult:
    if kind:
        items = [i for i in items if (i.get("kind") or "") == kind or kind == "all"]
    groups = group_items(items, probes=probes, min_copies=min_copies)
    extras = sum(max(0, len(g.copies) - 1) for g in groups)
    return CompareResult(
        groups=groups,
        item_count=len(items),
        group_count=len(groups),
        extra_copies=extras,
    )


def compare_catalog(
    catalog_path: str | Path | None = None,
    drive_ids: list[int] | None = None,
    kind: str | None = None,
    min_copies: int = 2,
    probes: dict[str, ProbeResult] | None = None,
) -> CompareResult:
    """
    Read Entertainment.Servers catalog.db and return duplicate groups
    with a recommended keeper per group.

    Deep probe is optional: pass `probes` keyed by file_path, or run
    mmc.pipeline.deep_scan_paths after importing.
    """
    from mmc.catalog_import import open_catalog

    path = open_catalog(catalog_path)
    items = load_catalog_items(path, drive_ids=drive_ids, kind=None if kind in {None, "all"} else kind)
    result = compare_items(items, probes=probes, min_copies=min_copies, kind=None)
    result.catalog_path = str(path)
    remote = any((i.get("source_type") or "") == "remote" for i in items)
    if remote:
        result.notes.append(
            "Most files are on the Windows agent. Filename + size scoring is used "
            "until the agent is upgraded (1.4+) and a deep scan is run."
        )
    return result


def score_one(item: dict[str, Any], probe: ProbeResult | None = None) -> QualityScore:
    return score_media(item, probe=probe)


score_item = score_one
