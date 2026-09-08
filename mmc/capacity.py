"""Fill missing drive capacity from local disk_usage or the Windows agent."""

from __future__ import annotations

import shutil
import threading
import time
from typing import Any

from mmc.catalog_import import list_catalog_drives, update_catalog_capacity
from mmc.remote_probe import RemoteProbeError, list_agent_drives


def _drive_letter(root_path: str | None) -> str:
    text = (root_path or "").strip().replace("\\", "/")
    if text and text[0].isalpha() and (len(text) == 1 or text[1] in ":/"):
        return text[0].upper()
    return ""

# Avoid stacking agent calls if the dashboard and fill request overlap.
_FILL_LOCK = threading.Lock()
_LAST_REMOTE_FAIL_AT = 0.0
_REMOTE_FAIL_COOLDOWN_S = 45.0


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n


def capacity_from_usage(root_path: str) -> dict[str, int] | None:
    """Local shutil.disk_usage. None if the path is not mounted here."""
    root = (root_path or "").strip()
    if not root:
        return None
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return None
    if not usage.total:
        return None
    return {
        "total_bytes": int(usage.total),
        "free_bytes": int(usage.free),
        "used_bytes": int(usage.used),
    }


def _norm_vol_key(text: str | None) -> str:
    return (text or "").strip().replace("\\", "/").rstrip("/").lower()


def index_agent_drives(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Map drive letter and/or path → {total,free,used} from GET /api/drives."""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        total = _int(row.get("total_bytes") or row.get("size_bytes"))
        free = _int(row.get("free_bytes"))
        used = _int(row.get("used_bytes"))
        if not total or total <= 0:
            continue
        if used is None and free is not None:
            used = max(0, total - free)
        if free is None and used is not None:
            free = max(0, total - used)
        cap = {
            "total_bytes": total,
            "free_bytes": free if free is not None else 0,
            "used_bytes": used if used is not None else max(0, total - (free or 0)),
        }
        letter = (row.get("letter") or "").strip()
        path = (row.get("path") or row.get("path_native") or letter or "").replace("\\", "/")
        win_letter = ""
        if letter and letter[0].isalpha() and (len(letter) == 1 or letter[1] in ":/\\"):
            win_letter = letter[0].upper()
        elif path and path[0].isalpha() and (len(path) == 1 or path[1] in ":/\\"):
            win_letter = path[0].upper()
        if win_letter:
            out[win_letter] = cap
        path_key = _norm_vol_key(path)
        if path_key:
            out[path_key] = cap
    return out


def needs_capacity(raw: dict[str, Any]) -> bool:
    total = _int(raw.get("capacity_total_bytes"))
    return not bool(total and total > 0)


def fill_unknown_drive_capacities(
    catalog_path: str | None = None,
    *,
    local: bool = True,
    remote: bool = True,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """
    Ask each unknown volume for a real size. Never invents numbers.

    Local: shutil.disk_usage on this machine.
    Remote: one GET /api/drives per media-host agent, matched by letter or path.
    Writes hits back to catalog.db so Media Catalog sees them too.
    """
    global _LAST_REMOTE_FAIL_AT
    summary: dict[str, Any] = {
        "filled": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }
    if not _FILL_LOCK.acquire(blocking=False):
        summary["skipped"] = -1
        summary["errors"].append("capacity fill already running")
        return summary
    try:
        try:
            rows = list_catalog_drives(catalog_path)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(str(exc))
            return summary

        unknown = [r for r in rows if needs_capacity(r)]
        if not unknown:
            return summary

        if local:
            for raw in unknown:
                if (raw.get("source_type") or "local") == "remote":
                    continue
                cap = capacity_from_usage(str(raw.get("root_path") or ""))
                if not cap:
                    continue
                if update_catalog_capacity(
                    int(raw["id"]),
                    cap["total_bytes"],
                    cap["free_bytes"],
                    cap["used_bytes"],
                    catalog_path=catalog_path,
                ):
                    summary["filled"] += 1
                    raw["capacity_total_bytes"] = cap["total_bytes"]

        still = [r for r in unknown if needs_capacity(r)]
        if not remote or not still:
            return summary

        now = time.time()
        if now - _LAST_REMOTE_FAIL_AT < _REMOTE_FAIL_COOLDOWN_S:
            summary["errors"].append("agent recently unreachable — retry shortly")
            return summary

        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for raw in still:
            if (raw.get("source_type") or "local") != "remote":
                continue
            url = (raw.get("agent_url") or "").strip()
            if not url:
                continue
            token = str(raw.get("agent_token") or "")
            groups.setdefault((url, token), []).append(raw)

        any_ok = False
        any_attempt = False
        for (url, token), members in groups.items():
            any_attempt = True
            try:
                listed = list_agent_drives(url, token=token, timeout=timeout)
                by_letter = index_agent_drives(listed)
            except RemoteProbeError as exc:
                summary["failed"] += 1
                summary["errors"].append(f"{url}: {exc}")
                continue
            any_ok = True
            for raw in members:
                root = raw.get("root_path")
                cap = by_letter.get(_drive_letter(root)) or by_letter.get(_norm_vol_key(root))
                if not cap:
                    continue
                if update_catalog_capacity(
                    int(raw["id"]),
                    cap["total_bytes"],
                    cap["free_bytes"],
                    cap["used_bytes"],
                    catalog_path=catalog_path,
                ):
                    summary["filled"] += 1

        if any_attempt and not any_ok:
            _LAST_REMOTE_FAIL_AT = time.time()
        return summary
    finally:
        _FILL_LOCK.release()
