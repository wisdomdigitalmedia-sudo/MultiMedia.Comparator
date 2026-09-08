"""Write path for Entertainment.Servers catalog.db (drives + media)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mmc.catalog_import import open_catalog
from mmc.config import DATA_DIR, DEFAULT_CATALOG_PATHS, find_catalog_db


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_catalog(catalog_path: str | Path | None = None) -> Path:
    """Open catalog.db, creating a sibling file if Media Catalog never ran."""
    found = find_catalog_db(catalog_path)
    if found:
        return found
    dest: Path
    if catalog_path:
        dest = Path(catalog_path).expanduser()
    else:
        dest = next((c for c in DEFAULT_CATALOG_PATHS if c.parent.is_dir()), DATA_DIR / "catalog.db")
    dest.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dest))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS drives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_scanned_at TEXT,
                item_count INTEGER DEFAULT 0,
                source_type TEXT DEFAULT 'local',
                agent_url TEXT DEFAULT '',
                agent_token TEXT DEFAULT '',
                capacity_total_bytes INTEGER,
                capacity_free_bytes INTEGER,
                capacity_used_bytes INTEGER,
                capacity_checked_at TEXT,
                hardware_type TEXT DEFAULT '',
                hardware_label TEXT DEFAULT '',
                volume_label TEXT DEFAULT '',
                smart_status TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS media_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drive_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                display_title TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                parent_folder TEXT DEFAULT '',
                kind TEXT DEFAULT 'movie',
                show_name TEXT,
                season INTEGER,
                episode INTEGER,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(drive_id, file_path),
                FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    return dest


def _connect(catalog_path: str | Path | None = None) -> sqlite3.Connection:
    path = open_catalog(catalog_path) if find_catalog_db(catalog_path) else ensure_catalog(catalog_path)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def normalize_windows_path(root_path: str) -> str:
    text = str(root_path or "").strip().strip('"').strip("'").replace("\\", "/")
    if re.fullmatch(r"[A-Za-z]", text):
        return f"{text.upper()}:/"
    if re.fullmatch(r"[A-Za-z]:/?", text):
        return f"{text[0].upper()}:/"
    missing = re.fullmatch(r"([A-Za-z]):([^/].*)", text)
    if missing:
        return f"{missing.group(1).upper()}:/{missing.group(2)}"
    headed = re.match(r"^([A-Za-z]):/(.*)$", text)
    if headed:
        rest = headed.group(2)
        return f"{headed.group(1).upper()}:/{rest}" if rest else f"{headed.group(1).upper()}:/"
    return text


def get_drive(drive_id: int, catalog_path: str | Path | None = None) -> dict[str, Any] | None:
    conn = _connect(catalog_path)
    try:
        row = conn.execute("SELECT * FROM drives WHERE id = ?", (int(drive_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_media(
    drive_id: int,
    q: str | None = None,
    kind: str | None = None,
    *,
    limit: int | None = None,
    offset: int = 0,
    catalog_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return (rows, total) for one catalog drive. Never invents files."""
    where = ["m.drive_id = ?"]
    params: list[Any] = [int(drive_id)]
    if q:
        like = f"%{q}%"
        where.append(
            "(m.display_title LIKE ? OR m.file_name LIKE ? OR m.relative_path LIKE ?)"
        )
        params.extend([like, like, like])
    if kind:
        where.append("m.kind = ?")
        params.append(kind)
    clause = " AND ".join(where)
    order = """
        CASE m.kind
            WHEN 'movie' THEN 0
            WHEN 'episode' THEN 1
            WHEN 'audio' THEN 2
            ELSE 3
        END,
        m.display_title COLLATE NOCASE,
        m.show_name COLLATE NOCASE,
        m.season,
        m.episode,
        m.file_name COLLATE NOCASE
    """
    conn = _connect(catalog_path)
    try:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) AS c FROM media_items m WHERE {clause}",
                params,
            ).fetchone()["c"]
        )
        sql = f"SELECT m.* FROM media_items m WHERE {clause} ORDER BY {order}"
        page_params = list(params)
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            page_params.extend([int(limit), int(offset)])
        rows = [dict(r) for r in conn.execute(sql, page_params).fetchall()]
        return rows, total
    finally:
        conn.close()


def path_parts(relative_path: str | None) -> list[str]:
    text = (relative_path or "").replace("\\", "/").strip("/")
    return [p for p in text.split("/") if p and p not in {".", ".."}]


def max_folder_depth(items: list[dict[str, Any]]) -> int:
    """Deepest directory count (excluding the file name)."""
    deepest = 0
    for item in items:
        parts = path_parts(item.get("relative_path"))
        if len(parts) > 1:
            deepest = max(deepest, len(parts) - 1)
    return deepest


def fold_by_depth(
    items: list[dict[str, Any]],
    depth: int,
    prefix: str = "",
) -> list[dict[str, Any]]:
    """
    Collapse files under a directory prefix into folder rows.

    depth=0 → every file (no collapse).
    depth=3 → Music/Artist/Album as one row instead of each track.
    """
    prefix_parts = path_parts(prefix)
    if depth <= 0:
        out = []
        for item in items:
            parts = path_parts(item.get("relative_path"))
            if prefix_parts and parts[: len(prefix_parts)] != prefix_parts:
                continue
            row = dict(item)
            row["is_folder"] = False
            out.append(row)
        return out

    folders: dict[str, dict[str, Any]] = {}
    files: list[dict[str, Any]] = []
    for item in items:
        parts = path_parts(item.get("relative_path"))
        if prefix_parts:
            if parts[: len(prefix_parts)] != prefix_parts:
                continue
            parts = parts[len(prefix_parts) :]
        if not parts:
            continue
        # Remaining path is only the file → list the file.
        if len(parts) <= depth:
            row = dict(item)
            row["is_folder"] = False
            files.append(row)
            continue
        key = "/".join(parts[:depth])
        folder = folders.get(key)
        if folder is None:
            shown = "/".join(prefix_parts + parts[:depth]) if prefix_parts else key
            folder = {
                "is_folder": True,
                "display_title": parts[depth - 1],
                "relative_path": shown,
                "file_name": parts[depth - 1],
                "file_count": 0,
                "size_bytes": 0,
                "kind": item.get("kind") or "other",
                "kinds": {},
                "extension": "",
            }
            folders[key] = folder
        folder["file_count"] += 1
        folder["size_bytes"] += int(item.get("size_bytes") or 0)
        k = item.get("kind") or "other"
        kinds = folder["kinds"]
        kinds[k] = int(kinds.get(k) or 0) + 1
        if folder["kind"] != k:
            folder["kind"] = "folder"
    folder_rows = sorted(folders.values(), key=lambda r: (r["relative_path"] or "").lower())
    file_rows = sorted(
        files,
        key=lambda r: (
            (r.get("display_title") or r.get("file_name") or "").lower(),
            (r.get("file_name") or "").lower(),
        ),
    )
    return folder_rows + file_rows


def delete_media_by_path(
    file_path: str, catalog_path: str | Path | None = None
) -> int:
    """Remove catalog rows for a file path. Updates drive item_count. Files on disk are not touched here."""
    raw = (file_path or "").strip()
    if not raw:
        return 0
    variants = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}
    conn = _connect(catalog_path)
    try:
        placeholders = ",".join("?" * len(variants))
        rows = conn.execute(
            f"SELECT id, drive_id FROM media_items WHERE file_path IN ({placeholders})",
            tuple(variants),
        ).fetchall()
        if not rows:
            return 0
        ids = [int(r["id"]) for r in rows]
        drive_ids = {int(r["drive_id"]) for r in rows}
        id_ph = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM media_items WHERE id IN ({id_ph})", ids)
        for drive_id in drive_ids:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM media_items WHERE drive_id = ?",
                (drive_id,),
            ).fetchone()["c"]
            conn.execute(
                "UPDATE drives SET item_count = ? WHERE id = ?",
                (int(count), drive_id),
            )
        conn.commit()
        return len(ids)
    finally:
        conn.close()


def get_setting(key: str, default: str = "", catalog_path: str | Path | None = None) -> str:
    conn = _connect(catalog_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(settings)")}
        if "key" not in cols:
            return default
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str, catalog_path: str | Path | None = None) -> None:
    conn = _connect(catalog_path)
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value if value is not None else ""),
        )
        conn.commit()
    finally:
        conn.close()


def _split_agent_url(url: str) -> tuple[str, str]:
    text = (url or "").strip()
    for prefix in ("http://", "https://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.rstrip("/")
    if ":" in text:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            return host, port
    return text, "8766"


def get_default_agent(catalog_path: str | Path | None = None) -> dict[str, str]:
    url = get_setting("agent_url", "", catalog_path)
    host = get_setting("agent_host", "", catalog_path)
    port = get_setting("agent_port", "8766", catalog_path) or "8766"
    token = get_setting("agent_token", "", catalog_path)
    if not url and not host:
        conn = _connect(catalog_path)
        try:
            row = conn.execute(
                """
                SELECT agent_url, agent_token FROM drives
                WHERE source_type = 'remote' AND IFNULL(agent_url, '') != ''
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            if row:
                url = row["agent_url"] or ""
                token = row["agent_token"] or token
        finally:
            conn.close()
    if url and not host:
        host, port = _split_agent_url(url)
    if host and not url:
        url = f"http://{host}:{port or '8766'}"
    return {
        "agent_url": url,
        "agent_host": host,
        "agent_port": port or "8766",
        "agent_token": token,
    }


def save_default_agent(
    agent_url: str = "",
    agent_host: str = "",
    agent_port: str = "8766",
    agent_token: str = "",
    catalog_path: str | Path | None = None,
) -> None:
    url = (agent_url or "").strip().rstrip("/")
    host = (agent_host or "").strip()
    port = (agent_port or "8766").strip() or "8766"
    token = (agent_token or "").strip()
    if not url and host:
        url = f"http://{host}:{port}"
    if url and not host:
        host, port = _split_agent_url(url)
    if url and not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    if url:
        set_setting("agent_url", url, catalog_path)
    if host:
        set_setting("agent_host", host, catalog_path)
    if port:
        set_setting("agent_port", port, catalog_path)
    set_setting("agent_token", token, catalog_path)


def add_drive(
    name: str,
    root_path: str,
    notes: str = "",
    source_type: str = "local",
    agent_url: str = "",
    agent_token: str = "",
    catalog_path: str | Path | None = None,
) -> int:
    source_type = (source_type or "local").strip().lower()
    if source_type not in {"local", "remote"}:
        raise ValueError("source_type must be local or remote")
    if source_type == "local":
        root = str(Path(root_path).expanduser().resolve())
        agent_url = ""
        agent_token = ""
    else:
        root = normalize_windows_path(root_path)
        agent_url = agent_url.strip().rstrip("/")
        if not agent_url:
            raise ValueError("agent_url is required for remote drives")
        if not agent_url.startswith("http://") and not agent_url.startswith("https://"):
            agent_url = "http://" + agent_url
        agent_token = agent_token.strip()

    conn = _connect(catalog_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO drives (
                name, root_path, notes, created_at,
                source_type, agent_url, agent_token
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name.strip(), root, notes.strip(), utc_now(), source_type, agent_url, agent_token),
        )
        conn.commit()
        return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"That path is already in the catalog ({root})."
        ) from exc
    finally:
        conn.close()


def delete_drive(drive_id: int, catalog_path: str | Path | None = None) -> dict[str, Any] | None:
    """Remove a drive and its catalog rows. Never touches files on disk."""
    existing = get_drive(drive_id, catalog_path)
    if not existing:
        return None
    conn = _connect(catalog_path)
    try:
        conn.execute("DELETE FROM media_items WHERE drive_id = ?", (int(drive_id),))
        conn.execute("DELETE FROM drives WHERE id = ?", (int(drive_id),))
        conn.commit()
        return existing
    finally:
        conn.close()


def upsert_media_items(
    drive_id: int,
    items: list[dict[str, Any]],
    catalog_path: str | Path | None = None,
) -> int:
    now = utc_now()
    conn = _connect(catalog_path)
    try:
        existing = {
            row["file_path"]: row["id"]
            for row in conn.execute(
                "SELECT id, file_path FROM media_items WHERE drive_id = ?",
                (int(drive_id),),
            )
        }
        seen: set[str] = set()
        for item in items:
            path = item.get("file_path") or ""
            if not path:
                continue
            seen.add(path)
            payload = (
                item.get("relative_path") or "",
                item.get("file_name") or "",
                item.get("display_title") or item.get("file_name") or "",
                item.get("extension") or "",
                int(item.get("size_bytes") or 0),
                item.get("parent_folder") or "",
                item.get("kind") or "movie",
                item.get("show_name"),
                item.get("season"),
                item.get("episode"),
                now,
            )
            if path in existing:
                conn.execute(
                    """
                    UPDATE media_items SET
                        relative_path = ?, file_name = ?, display_title = ?,
                        extension = ?, size_bytes = ?, parent_folder = ?,
                        kind = ?, show_name = ?, season = ?, episode = ?,
                        last_seen_at = ?
                    WHERE id = ?
                    """,
                    (*payload, existing[path]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO media_items (
                        drive_id, file_path, relative_path, file_name,
                        display_title, extension, size_bytes, parent_folder,
                        kind, show_name, season, episode,
                        first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (int(drive_id), path, *payload[:-1], now, now),
                )
        gone = set(existing) - seen
        if gone:
            conn.executemany(
                "DELETE FROM media_items WHERE drive_id = ? AND file_path = ?",
                [(int(drive_id), p) for p in gone],
            )
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM media_items WHERE drive_id = ?",
            (int(drive_id),),
        ).fetchone()["c"]
        conn.execute(
            "UPDATE drives SET last_scanned_at = ?, item_count = ? WHERE id = ?",
            (now, int(count), int(drive_id)),
        )
        conn.commit()
        return int(count)
    finally:
        conn.close()
