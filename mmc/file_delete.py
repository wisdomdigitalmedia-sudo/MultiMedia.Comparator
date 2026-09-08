"""Delete one ranked duplicate copy from disk and the catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mmc.catalog_store import delete_media_by_path
from mmc.config import MEDIA_EXTENSIONS
from mmc.db import delete_items_by_path
from mmc.grouper import DuplicateGroup, ScoredCopy
from mmc.remote_probe import RemoteProbeError, delete_remote_file
from mmc.scanner import format_size


class DeleteError(Exception):
    pass


def find_copy(
    groups: list[DuplicateGroup], path: str
) -> tuple[DuplicateGroup, ScoredCopy] | None:
    want = (path or "").replace("\\", "/").rstrip()
    if not want:
        return None
    for group in groups:
        for copy in group.copies:
            have = (copy.item.get("file_path") or "").replace("\\", "/").rstrip()
            if have == want:
                return group, copy
    return None


def copy_summary(copy: ScoredCopy) -> dict[str, Any]:
    item = copy.item
    size = int(item.get("size_bytes") or 0)
    return {
        "path": item.get("file_path") or "",
        "name": item.get("file_name") or "",
        "drive": item.get("drive_name") or "",
        "size_label": format_size(size),
        "is_keep": bool(copy.is_winner),
        "score": copy.score.total,
        "summary": copy.score.summary,
    }


def _unlink_local(path: str) -> None:
    target = Path(path)
    if target.is_dir():
        raise DeleteError("Refusing to delete a directory.")
    suffix = target.suffix.lower()
    if suffix and suffix not in MEDIA_EXTENSIONS:
        raise DeleteError(f"Refusing to delete a non-media file ({suffix}).")
    if target.is_file():
        try:
            target.unlink()
        except OSError as exc:
            raise DeleteError(f"Could not delete local file: {exc}") from exc
        return
    if target.exists():
        raise DeleteError("Path exists but is not a file.")


def delete_copy_file(copy: ScoredCopy) -> str:
    """Remove the file from disk. Returns a short status for the flash."""
    item = copy.item
    path = str(item.get("file_path") or "")
    if not path:
        raise DeleteError("Copy has no file path.")
    source_type = (item.get("source_type") or "").lower()
    agent_url = str(item.get("agent_url") or "")
    local = Path(path)
    if source_type == "remote" or (agent_url and not local.is_file()):
        if not agent_url:
            raise DeleteError(
                "This file is on the Windows PC but has no agent URL. "
                "Re-import the catalog, then try again."
            )
        try:
            report = delete_remote_file(
                agent_url, path, token=str(item.get("agent_token") or "")
            )
        except RemoteProbeError as exc:
            raise DeleteError(str(exc)) from exc
        if report.get("already_gone"):
            return "already missing on disk"
        return "deleted on the media host"
    _unlink_local(path)
    return "deleted on this PC"


def forget_copy(path: str) -> None:
    """Drop catalog + comparator rows after the file is gone."""
    delete_media_by_path(path)
    delete_items_by_path(path)


def drop_copy_from_groups(
    groups: list[DuplicateGroup], path: str
) -> list[DuplicateGroup]:
    want = (path or "").replace("\\", "/").rstrip()
    out: list[DuplicateGroup] = []
    for group in groups:
        copies = [
            c
            for c in group.copies
            if (c.item.get("file_path") or "").replace("\\", "/").rstrip() != want
        ]
        if len(copies) < 2:
            continue
        if not any(c.is_winner for c in copies):
            copies.sort(key=lambda c: (c.rank or 99, -c.score.total))
            for i, copy in enumerate(copies, start=1):
                copy.rank = i
                copy.is_winner = i == 1
        extras = [c for c in copies if not c.is_winner]
        winner = next((c for c in copies if c.is_winner), copies[0])
        group.copies = copies
        group.score_gap = (
            round(winner.score.total - extras[0].score.total, 1) if extras else 0.0
        )
        out.append(group)
    return out
