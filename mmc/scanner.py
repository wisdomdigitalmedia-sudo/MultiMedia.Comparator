"""Walk local folders and collect media files (expanded codec set)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mmc.config import (
    AUDIO_EXTENSIONS,
    IGNORE_EXTENSIONS,
    IGNORE_FOLDER_NAMES,
    IGNORE_NAME_MARKERS,
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from mmc.identity import identify


def path_has_ignored_folder(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    for part in relative.parts[:-1]:
        if part.lower() in IGNORE_FOLDER_NAMES:
            return True
        if part.startswith(".") and part not in (".", ".."):
            return True
    return False


def is_ignored_file(path: Path) -> bool:
    name_lower = path.name.lower()
    ext = path.suffix.lower()
    if ext in IGNORE_EXTENSIONS:
        return True
    if ext not in MEDIA_EXTENSIONS:
        return True
    if name_lower.startswith("."):
        return True
    for marker in IGNORE_NAME_MARKERS:
        if marker in name_lower:
            return True
    stem = path.stem.lower()
    if stem in {"sample", "proof"} or stem.startswith("sample.") or stem.endswith(".sample"):
        return True
    return False


def scan_root(root_path: str | Path, source_name: str = "") -> list[dict[str, Any]]:
    root = Path(root_path).expanduser()
    try:
        root = root.resolve()
    except OSError:
        pass
    if not root.is_dir():
        raise FileNotFoundError(f"Path is not a directory or not mounted: {root}")

    results: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        pruned = []
        for d in dirnames:
            low = d.lower()
            if low in IGNORE_FOLDER_NAMES or (d.startswith(".") and d not in (".", "..")):
                continue
            pruned.append(d)
        dirnames[:] = pruned

        current = Path(dirpath)
        if path_has_ignored_folder(current / "x", root):
            dirnames[:] = []
            continue

        for name in filenames:
            path = current / name
            if is_ignored_file(path):
                continue
            if path_has_ignored_folder(path, root):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = path.name
            ext = path.suffix.lower()
            if ext in AUDIO_EXTENSIONS:
                kind = "audio"
            elif ext in VIDEO_EXTENSIONS:
                kind = "movie"
            else:
                kind = "other"
            item = {
                "file_path": str(path),
                "relative_path": rel,
                "file_name": path.name,
                "display_title": path.stem,
                "extension": ext,
                "size_bytes": size,
                "parent_folder": path.parent.name,
                "kind": kind,
                "show_name": None,
                "season": None,
                "episode": None,
                "source_name": source_name or root.name,
                "drive_name": source_name or root.name,
            }
            ident = identify(item)
            item["kind"] = ident.kind
            item["display_title"] = ident.label
            item["show_name"] = ident.show
            item["season"] = ident.season
            item["episode"] = ident.episode
            results.append(item)
    return results


def format_size(num: int | None) -> str:
    if num is None:
        return "—"
    value = float(num)
    if value < 1024:
        return f"{int(value)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"
