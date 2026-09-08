"""Add, scan, and remove catalog drives from the Comparator UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mmc.catalog_import import list_catalog_drives
from mmc.catalog_store import (
    add_drive,
    delete_drive,
    get_drive,
    normalize_windows_path,
    save_default_agent,
    upsert_media_items,
)
from mmc.identity import identify
from mmc.pipeline import import_entertainment_catalog
from mmc.remote_probe import RemoteProbeError, agent_health, list_agent_drives, scan_remote_path
from mmc.scanner import scan_root


class DriveOpsError(Exception):
    pass


def _classify(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        ident = identify(item)
        item["kind"] = ident.kind
        item["display_title"] = ident.label or item.get("display_title") or item.get("file_name")
        if ident.show:
            item["show_name"] = ident.show
        if ident.season is not None:
            item["season"] = ident.season
        if ident.episode is not None:
            item["episode"] = ident.episode
        out.append(item)
    return out


def sync_comparator_library(catalog_path: str | Path | None = None) -> tuple[int, int] | None:
    """Reload comparator.db from catalog.db after a drive change."""
    try:
        return import_entertainment_catalog(catalog_path)
    except FileNotFoundError:
        return None


def add_local_drive(
    name: str,
    root_path: str,
    notes: str = "",
    catalog_path: str | Path | None = None,
) -> int:
    path = Path(root_path).expanduser()
    if not path.is_dir():
        raise DriveOpsError(
            f"Path not found or not a directory (is the share mounted?): {path}"
        )
    label = (name or path.name or str(path)).strip()
    return add_drive(label, str(path), notes=notes, source_type="local", catalog_path=catalog_path)


def add_remote_drive(
    name: str,
    root_path: str,
    agent_url: str,
    agent_token: str = "",
    agent_host: str = "",
    agent_port: str = "8766",
    notes: str = "",
    catalog_path: str | Path | None = None,
) -> int:
    url = (agent_url or "").strip()
    if not url and agent_host:
        url = f"http://{agent_host.strip()}:{agent_port or '8766'}"
    if not url:
        raise DriveOpsError("Media host address (agent URL or host) is required.")
    try:
        agent_health(url, token=agent_token)
    except RemoteProbeError as exc:
        raise DriveOpsError(str(exc)) from exc
    remote = normalize_windows_path(root_path)
    letter = remote[:1].upper() if remote else ""
    label = (name or (f"{letter}:" if letter else remote)).strip()
    drive_id = add_drive(
        label,
        remote,
        notes=notes,
        source_type="remote",
        agent_url=url,
        agent_token=agent_token,
        catalog_path=catalog_path,
    )
    save_default_agent(
        agent_url=url,
        agent_host=agent_host,
        agent_port=agent_port,
        agent_token=agent_token,
        catalog_path=catalog_path,
    )
    return drive_id


def list_windows_volumes(
    agent_url: str,
    token: str = "",
    catalog_path: str | Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    info = agent_health(agent_url, token=token)
    rows = list_agent_drives(agent_url, token=token)
    existing = list_catalog_drives(catalog_path)
    taken_letters = {
        ((d.get("root_path") or "")[:1].upper())
        for d in existing
        if (d.get("source_type") or "") == "remote"
        and (d.get("agent_url") or "").rstrip("/") == agent_url.rstrip("/")
        and (d.get("root_path") or "")[1:2] == ":"
    }
    taken_paths = {
        (d.get("root_path") or "").replace("\\", "/").lower().rstrip("/")
        for d in existing
        if (d.get("source_type") or "") == "remote"
    }
    for row in rows:
        raw_letter = str(row.get("letter") or "").strip()
        path = (row.get("path") or raw_letter or "").replace("\\", "/")
        path_key = path.lower().rstrip("/")
        win_letter = ""
        if raw_letter and raw_letter[0].isalpha() and (
            len(raw_letter) == 1 or raw_letter[1] in ":/\\"
        ):
            win_letter = raw_letter[0].upper()
        elif path and path[0].isalpha() and (len(path) == 1 or path[1] in ":/"):
            win_letter = path[0].upper()
        row["already_added"] = bool(
            (win_letter and win_letter in taken_letters) or path_key in taken_paths
        )
        row["display"] = row.get("display") or path or raw_letter
        row["path"] = path or raw_letter
    return info, rows


def scan_drive(drive_id: int, catalog_path: str | Path | None = None) -> tuple[str, int]:
    drive = get_drive(drive_id, catalog_path)
    if not drive:
        raise DriveOpsError("Drive not found.")
    name = drive.get("name") or f"#{drive_id}"
    source = (drive.get("source_type") or "local").lower()
    if source == "remote":
        url = (drive.get("agent_url") or "").strip()
        if not url:
            raise DriveOpsError(f"{name} has no agent URL.")
        root = normalize_windows_path(drive.get("root_path") or "")
        try:
            found = scan_remote_path(
                url,
                root,
                token=str(drive.get("agent_token") or ""),
            )
        except RemoteProbeError as exc:
            raise DriveOpsError(str(exc)) from exc
    else:
        found = scan_root(drive.get("root_path") or "", source_name=name)
    found = _classify(found)
    count = upsert_media_items(drive_id, found, catalog_path=catalog_path)
    return name, count


def remove_drive(drive_id: int, catalog_path: str | Path | None = None) -> str:
    removed = delete_drive(drive_id, catalog_path)
    if not removed:
        raise DriveOpsError("Drive not found.")
    return str(removed.get("name") or f"#{drive_id}")
