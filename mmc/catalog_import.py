"""Load media rows from an Entertainment.Servers catalog.db."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mmc.config import find_catalog_db


def open_catalog(path: str | Path | None = None) -> Path:
    found = find_catalog_db(path)
    if not found:
        raise FileNotFoundError(
            "Entertainment.Servers catalog.db not found. "
            "Pass the path or add the sibling project on the Desktop."
        )
    return found


def list_catalog_drives(catalog_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = open_catalog(catalog_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(drives)")}
        extra = [
            c
            for c in (
                "capacity_total_bytes",
                "capacity_free_bytes",
                "capacity_used_bytes",
                "capacity_checked_at",
                "hardware_type",
                "hardware_label",
                "smart_status",
                "volume_label",
                "agent_token",
            )
            if c in cols
        ]
        select = "id, name, root_path, item_count, source_type, agent_url"
        if extra:
            select += ", " + ", ".join(extra)
        rows = conn.execute(
            f"SELECT {select} FROM drives ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_catalog_items(
    catalog_path: str | Path | None = None,
    drive_ids: list[int] | None = None,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    """Return items shaped for identify() / group_items()."""
    path = open_catalog(catalog_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT m.id AS catalog_id, m.drive_id, m.file_path, m.relative_path,
                   m.file_name, m.display_title, m.extension, m.size_bytes,
                   m.parent_folder, m.kind, m.show_name, m.season, m.episode,
                   d.name AS drive_name, d.root_path AS drive_root,
                   d.source_type, d.agent_url, d.agent_token
            FROM media_items m
            JOIN drives d ON d.id = m.drive_id
            WHERE 1=1
        """
        params: list[Any] = []
        if drive_ids:
            placeholders = ",".join("?" * len(drive_ids))
            sql += f" AND m.drive_id IN ({placeholders})"
            params.extend(drive_ids)
        if kind:
            sql += " AND m.kind = ?"
            params.append(kind)
        rows = conn.execute(sql, params).fetchall()
        items: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["source_name"] = item.get("drive_name") or ""
            item["id"] = f"cat:{item.get('catalog_id')}"
            items.append(item)
        return items
    finally:
        conn.close()


def update_catalog_capacity(
    drive_id: int,
    total_bytes: int | None,
    free_bytes: int | None,
    used_bytes: int | None = None,
    catalog_path: str | Path | None = None,
) -> bool:
    """Write volume size/free back to Entertainment.Servers catalog.db."""
    if total_bytes is None and free_bytes is None:
        return False
    if used_bytes is None and total_bytes is not None and free_bytes is not None:
        used_bytes = max(0, int(total_bytes) - int(free_bytes))
    path = open_catalog(catalog_path)
    conn = sqlite3.connect(str(path), timeout=8)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(drives)")}
        needed = {
            "capacity_total_bytes",
            "capacity_free_bytes",
            "capacity_used_bytes",
            "capacity_checked_at",
        }
        if not needed.issubset(cols):
            return False
        checked = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        cur = conn.execute(
            """
            UPDATE drives SET
                capacity_total_bytes = ?,
                capacity_free_bytes = ?,
                capacity_used_bytes = ?,
                capacity_checked_at = ?
            WHERE id = ?
            """,
            (total_bytes, free_bytes, used_bytes, checked, int(drive_id)),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
