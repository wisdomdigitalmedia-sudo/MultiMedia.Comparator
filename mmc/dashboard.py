"""Assemble dashboard payloads: drive free space + library counters."""

from __future__ import annotations

from typing import Any

from mmc.catalog_import import list_catalog_drives, open_catalog
from mmc.config import find_catalog_db
from mmc.pipeline import stats as pipeline_stats
from mmc.scanner import format_size


def drive_letter(root_path: str | None) -> str:
    text = (root_path or "").strip().replace("\\", "/")
    if text and text[0].isalpha() and (len(text) == 1 or text[1] in ":/"):
        return text[0].upper()
    return ""


def free_pct(total: int | None, free: int | None) -> float | None:
    if not total or total <= 0 or free is None:
        return None
    return max(0.0, min(100.0, (float(free) / float(total)) * 100.0))


def used_pct(total: int | None, used: int | None, free: int | None) -> float | None:
    if not total or total <= 0:
        return None
    if used is None and free is not None:
        used = max(0, int(total) - int(free))
    if used is None:
        return None
    return max(0.0, min(100.0, (float(used) / float(total)) * 100.0))


def space_tone(pct_free: float | None) -> str:
    if pct_free is None:
        return "unknown"
    if pct_free <= 4:
        return "critical"
    if pct_free < 12:
        return "warn"
    return "ok"


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def enrich_drive(raw: dict[str, Any]) -> dict[str, Any]:
    total = _int(raw.get("capacity_total_bytes"))
    free = _int(raw.get("capacity_free_bytes"))
    used = _int(raw.get("capacity_used_bytes"))
    if used is None and total is not None and free is not None:
        used = max(0, total - free)
    known = bool(total and total > 0)
    fp = free_pct(total, free) if known else None
    up = used_pct(total, used, free) if known else None
    letter = drive_letter(raw.get("root_path"))
    return {
        "id": raw.get("id"),
        "name": raw.get("name") or letter or "Drive",
        "letter": letter,
        "root_path": raw.get("root_path") or "",
        "item_count": int(raw.get("item_count") or 0),
        "source_type": raw.get("source_type") or "local",
        "hardware_type": raw.get("hardware_type") or "unknown",
        "hardware_label": raw.get("hardware_label") or "Unknown hardware",
        "smart_status": raw.get("smart_status") or "",
        "volume_label": raw.get("volume_label") or "",
        "capacity_known": known,
        "total_bytes": total if known else None,
        "free_bytes": free if known else None,
        "used_bytes": used if known else None,
        "total_label": format_size(total) if known else "Size unknown",
        "free_label": format_size(free) if known else "—",
        "used_label": format_size(used) if known else "—",
        "free_pct": round(fp, 2) if fp is not None else None,
        "used_pct": round(up, 2) if up is not None else None,
        "tone": space_tone(fp),
    }


def load_drive_cards(catalog_path: str | None = None) -> list[dict[str, Any]]:
    try:
        open_catalog(catalog_path)
    except FileNotFoundError:
        return []
    try:
        rows = list_catalog_drives(catalog_path)
    except Exception:  # noqa: BLE001
        return []
    cards = [enrich_drive(dict(r)) for r in rows]
    cards.sort(
        key=lambda d: (
            0 if d["capacity_known"] else 1,
            d["free_pct"] if d["free_pct"] is not None else 999,
            (d["name"] or "").lower(),
        )
    )
    return cards


def build_dashboard(
    catalog_path: str | None = None,
    *,
    fill_unknown: bool = False,
    fill_remote: bool = False,
) -> dict[str, Any]:
    """Single payload for the home dashboard and /api/dashboard."""
    fill_info: dict[str, Any] | None = None
    if fill_unknown:
        try:
            from mmc.capacity import fill_unknown_drive_capacities

            fill_info = fill_unknown_drive_capacities(
                catalog_path, local=True, remote=fill_remote
            )
        except Exception:  # noqa: BLE001
            fill_info = {"filled": 0, "failed": 1, "errors": ["capacity fill crashed"]}
    lib = pipeline_stats()
    drives = load_drive_cards(catalog_path)
    known = [d for d in drives if d["capacity_known"]]
    unknown = [d for d in drives if not d["capacity_known"]]
    total = sum(int(d["total_bytes"] or 0) for d in known)
    free = sum(int(d["free_bytes"] or 0) for d in known)
    used = sum(int(d["used_bytes"] or 0) for d in known)
    fp = free_pct(total, free)
    kinds = lib.get("kinds") or {}
    tightest = [d for d in known if (d["free_pct"] or 100) < 10][:4]
    return {
        "catalog_path": str(find_catalog_db(catalog_path) or ""),
        "has_catalog": bool(find_catalog_db(catalog_path)),
        "drives": drives,
        "known_drives": known,
        "unknown_drives": unknown,
        "space": {
            "known_count": len(known),
            "unknown_count": len(unknown),
            "drive_count": len(drives),
            "total_bytes": total or None,
            "free_bytes": free if known else None,
            "used_bytes": used if known else None,
            "total_label": format_size(total) if known else "—",
            "free_label": format_size(free) if known else "—",
            "used_label": format_size(used) if known else "—",
            "free_pct": round(fp, 2) if fp is not None else None,
            "used_pct": round(100.0 - fp, 2) if fp is not None else None,
            "tone": space_tone(fp),
        },
        "library": {
            "sources": len(lib.get("sources") or []),
            "item_count": int(lib.get("item_count") or 0),
            "movies": int(kinds.get("movie") or 0),
            "episodes": int(kinds.get("episode") or 0),
            "audio": int(kinds.get("audio") or 0),
            "other": int(kinds.get("other") or 0),
        },
        "tightest": tightest,
        "capacity_fill": fill_info,
    }
