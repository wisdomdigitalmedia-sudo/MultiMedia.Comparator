"""Scan / import → identify → group → optional deep probe → rescore."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mmc import db
from mmc.catalog_import import load_catalog_items, open_catalog
from mmc.grouper import DuplicateGroup, group_items
from mmc.identity import identify
from mmc.probe import ProbeResult, probe_file, probe_from_dict
from mmc.remote_probe import RemoteProbeError, probe_remote_files
from mmc.scanner import scan_root

ProgressFn = Callable[[str, int, int], None]


def _attach_identity(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        ident = identify(item)
        item = dict(item)
        item["identity_key"] = ident.key
        item["identity_label"] = ident.label
        item["edition"] = ident.edition
        item["kind"] = ident.kind
        item["is_3d"] = ident.is_3d
        if ident.show:
            item["show_name"] = ident.show
        if ident.season is not None:
            item["season"] = ident.season
        if ident.episode is not None:
            item["episode"] = ident.episode
        out.append(item)
    return out


def import_entertainment_catalog(
    catalog_path: str | Path | None = None,
    drive_ids: list[int] | None = None,
    source_name: str = "Entertainment.Servers",
) -> tuple[int, int]:
    """Load catalog.db into the comparator store. Returns (source_id, item_count)."""
    db.init_db()
    path = open_catalog(catalog_path)
    items = load_catalog_items(path, drive_ids=drive_ids)
    items = _attach_identity(items)
    source_id = db.add_source(source_name, "catalog", str(path))
    count = db.replace_source_items(source_id, items)
    return source_id, count


def import_folder(root_path: str | Path, name: str = "") -> tuple[int, int]:
    db.init_db()
    root = str(Path(root_path).expanduser().resolve())
    label = name or Path(root).name or root
    items = scan_root(root, source_name=label)
    items = _attach_identity(items)
    source_id = db.add_source(label, "folder", root)
    count = db.replace_source_items(source_id, items)
    return source_id, count


def _probe_map_from_cache(paths: list[str]) -> dict[str, ProbeResult]:
    cached = db.load_probes(paths)
    return {p: probe_from_dict(blob) for p, blob in cached.items()}


def deep_scan_paths(
    items: list[dict[str, Any]],
    progress: ProgressFn | None = None,
    remote: bool = True,
    skip_cached: bool = True,
) -> dict[str, ProbeResult]:
    """
    Probe each item if the file is local. Optionally batch-probe remotes
    via the Windows agent (agent 1.4+).
    """
    db.init_db()
    paths = [str(i.get("file_path") or "") for i in items if i.get("file_path")]
    existing = _probe_map_from_cache(paths) if skip_cached else {}
    remaining = [it for it in items if str(it.get("file_path") or "") not in existing]

    local: list[dict[str, Any]] = []
    remote_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in remaining:
        path = Path(str(it.get("file_path") or ""))
        extra_type = it.get("source_type") or ""
        if extra_type == "remote" or (it.get("agent_url") and not path.is_file()):
            key = (str(it.get("agent_url") or ""), str(it.get("agent_token") or ""))
            remote_groups.setdefault(key, []).append(it)
        else:
            local.append(it)

    total = len(local) + sum(len(v) for v in remote_groups.values())
    done = 0

    if local:
        from mmc.ffprobe_install import FfprobeInstallError, ensure_ffprobe

        try:
            ensure_ffprobe(force=False)
        except FfprobeInstallError:
            # probe_file will surface the same error per item
            pass

    for it in local:
        path = str(it.get("file_path") or "")
        if not path:
            continue
        result = probe_file(path)
        db.save_probe(path, result.as_dict())
        existing[path] = result
        done += 1
        if progress:
            progress("local-probe", done, total)

    if remote:
        from mmc.remote_probe import ensure_remote_ffprobe

        for (agent_url, token), group in remote_groups.items():
            if not agent_url:
                continue
            try:
                ensure_remote_ffprobe(agent_url, token=token, force=False)
            except RemoteProbeError:
                # Old agent or offline — probe loop still tries /api/probe
                pass
            batch_size = 8
            for i in range(0, len(group), batch_size):
                batch = group[i : i + batch_size]
                batch_paths = [str(x.get("file_path") or "") for x in batch]
                try:
                    rows = probe_remote_files(agent_url, batch_paths, token=token)
                except RemoteProbeError:
                    # Agent too old or unreachable — skip; filename scoring still works
                    done += len(batch)
                    if progress:
                        progress("remote-probe-skip", done, total)
                    continue
                by_path = {str(r.get("path") or ""): r for r in rows if isinstance(r, dict)}
                for p in batch_paths:
                    blob = by_path.get(p) or {"ok": False, "tool": "agent", "path": p, "error": "no result"}
                    result = probe_from_dict(blob)
                    db.save_probe(p, result.as_dict())
                    existing[p] = result
                done += len(batch)
                if progress:
                    progress("remote-probe", done, total)

    return existing


def compare_loaded(
    min_copies: int = 2,
    kind: str | None = None,
    probes: dict[str, ProbeResult] | None = None,
) -> list[DuplicateGroup]:
    db.init_db()
    items = db.load_all_items()
    if kind:
        items = [i for i in items if i.get("kind") == kind]
    if probes is None:
        paths = [str(i.get("file_path") or "") for i in items]
        cached = db.load_probes(paths)
        probes = {p: probe_from_dict(blob) for p, blob in cached.items()}
    return group_items(items, probes=probes, min_copies=min_copies)


def stats() -> dict[str, Any]:
    db.init_db()
    return db.library_counts()
