"""SQLite persistence for drives, media items, and tags."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config import DATABASE_PATH, DATA_DIR


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
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
                agent_token TEXT DEFAULT ''
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
                kind TEXT DEFAULT 'movie',  -- movie | episode | other
                show_name TEXT,
                season INTEGER,
                episode INTEGER,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(drive_id, file_path),
                FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE
            );

            CREATE TABLE IF NOT EXISTS media_tags (
                media_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (media_id, tag_id),
                FOREIGN KEY (media_id) REFERENCES media_items(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS drive_tags (
                drive_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (drive_id, tag_id),
                FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_media_drive ON media_items(drive_id);
            CREATE INDEX IF NOT EXISTS idx_media_title ON media_items(display_title);
            CREATE INDEX IF NOT EXISTS idx_media_kind ON media_items(kind);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        _migrate_drives(conn)


def get_setting(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value if value is not None else ""),
        )


def get_default_agent() -> dict[str, str]:
    """Last-used Windows agent connection (auto-filled on Add drive)."""
    url = get_setting("agent_url", "")
    host = get_setting("agent_host", "")
    port = get_setting("agent_port", "8766") or "8766"
    token = get_setting("agent_token", "")

    # Fall back to most recently added remote drive
    if not url and not host:
        with db() as conn:
            row = conn.execute(
                """
                SELECT agent_url, agent_token FROM drives
                WHERE source_type = 'remote' AND agent_url IS NOT NULL AND agent_url != ''
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            if row:
                url = row["agent_url"] or ""
                token = row["agent_token"] or token

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
) -> None:
    """Remember agent host for next Add drive."""
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
        set_setting("agent_url", url)
    if host:
        set_setting("agent_host", host)
    if port:
        set_setting("agent_port", port)
    # Always save token (may clear intentionally)
    set_setting("agent_token", token)


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


def _migrate_drives(conn: sqlite3.Connection) -> None:
    """Add remote-agent columns and relax old UNIQUE(root_path) if present."""
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(drives)").fetchall()
    }
    if "source_type" not in cols:
        conn.execute(
            "ALTER TABLE drives ADD COLUMN source_type TEXT DEFAULT 'local'"
        )
    if "agent_url" not in cols:
        conn.execute(
            "ALTER TABLE drives ADD COLUMN agent_url TEXT DEFAULT ''"
        )
    if "agent_token" not in cols:
        conn.execute(
            "ALTER TABLE drives ADD COLUMN agent_token TEXT DEFAULT ''"
        )

    smart_cols = {
        "smart_status": "TEXT DEFAULT ''",
        "smart_status_raw": "TEXT DEFAULT ''",
        "smart_temperature_c": "INTEGER",
        "smart_model": "TEXT DEFAULT ''",
        "smart_serial": "TEXT DEFAULT ''",
        "smart_media": "TEXT DEFAULT ''",
        "smart_bus": "TEXT DEFAULT ''",
        "hardware_type": "TEXT DEFAULT ''",
        "hardware_label": "TEXT DEFAULT ''",
        "smart_source": "TEXT DEFAULT ''",
        "smart_detail": "TEXT DEFAULT ''",
        "smart_json": "TEXT DEFAULT ''",
        "smart_checked_at": "TEXT",
        "sector_attrs_available": "INTEGER DEFAULT 0",
        "sector_reallocated": "INTEGER",
        "sector_pending": "INTEGER",
        "sector_uncorrectable": "INTEGER",
        "sector_crc": "INTEGER",
        "sector_reported_uncorrect": "INTEGER",
        "nvme_media_errors": "INTEGER",
        "sector_summary": "TEXT DEFAULT ''",
        "volume_label": "TEXT DEFAULT ''",
        "capacity_total_bytes": "INTEGER",
        "capacity_free_bytes": "INTEGER",
        "capacity_used_bytes": "INTEGER",
        "capacity_checked_at": "TEXT",
    }
    # refresh cols after prior alters
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(drives)").fetchall()
    }
    for col, decl in smart_cols.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE drives ADD COLUMN {col} {decl}")

    # Older DBs created root_path as UNIQUE — rebuild if needed so remote
    # paths on different PCs can share the same letter (e.g. D:\).
    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='drives'"
    ).fetchone()
    sql = (create_sql["sql"] if create_sql else "") or ""
    if "root_path TEXT NOT NULL UNIQUE" in sql:
        conn.executescript(
            """
            CREATE TABLE drives_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_scanned_at TEXT,
                item_count INTEGER DEFAULT 0,
                source_type TEXT DEFAULT 'local',
                agent_url TEXT DEFAULT '',
                agent_token TEXT DEFAULT ''
            );
            INSERT INTO drives_migrated (
                id, name, root_path, notes, created_at, last_scanned_at,
                item_count, source_type, agent_url, agent_token
            )
            SELECT
                id, name, root_path, notes, created_at, last_scanned_at,
                item_count,
                COALESCE(source_type, 'local'),
                COALESCE(agent_url, ''),
                COALESCE(agent_token, '')
            FROM drives;
            DROP TABLE drives;
            ALTER TABLE drives_migrated RENAME TO drives;
            """
        )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_drives_identity
        ON drives(source_type, agent_url, root_path)
        """
    )


# --- Drives ---


def list_drives() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM drives ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def get_drive(drive_id: int) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM drives WHERE id = ?", (drive_id,)
        ).fetchone()
        return dict(row) if row else None


def add_drive(
    name: str,
    root_path: str,
    notes: str = "",
    source_type: str = "local",
    agent_url: str = "",
    agent_token: str = "",
) -> int:
    source_type = (source_type or "local").strip().lower()
    if source_type not in {"local", "remote"}:
        raise ValueError("source_type must be local or remote")
    if source_type == "local":
        root = str(Path(root_path).expanduser().resolve())
        agent_url = ""
        agent_token = ""
    else:
        root = root_path.strip()
        agent_url = agent_url.strip().rstrip("/")
        if not agent_url:
            raise ValueError("agent_url is required for remote drives")
        if not agent_url.startswith("http://") and not agent_url.startswith(
            "https://"
        ):
            agent_url = "http://" + agent_url
        agent_token = agent_token.strip()

    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO drives (
                name, root_path, notes, created_at,
                source_type, agent_url, agent_token
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                root,
                notes.strip(),
                utc_now(),
                source_type,
                agent_url,
                agent_token,
            ),
        )
        return int(cur.lastrowid)


def update_drive(
    drive_id: int,
    name: str,
    root_path: str,
    notes: str = "",
    source_type: str | None = None,
    agent_url: str | None = None,
    agent_token: str | None = None,
) -> None:
    existing = get_drive(drive_id)
    if not existing:
        raise ValueError("Drive not found")

    source = (source_type or existing.get("source_type") or "local").strip().lower()
    if source == "local":
        root = str(Path(root_path).expanduser().resolve())
        url = ""
        token = ""
    else:
        root = root_path.strip()
        url = (
            agent_url
            if agent_url is not None
            else (existing.get("agent_url") or "")
        ).strip().rstrip("/")
        if url and not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url
        token = (
            agent_token
            if agent_token is not None
            else (existing.get("agent_token") or "")
        ).strip()

    with db() as conn:
        conn.execute(
            """
            UPDATE drives
            SET name = ?, root_path = ?, notes = ?,
                source_type = ?, agent_url = ?, agent_token = ?
            WHERE id = ?
            """,
            (name.strip(), root, notes.strip(), source, url, token, drive_id),
        )


def delete_drive(drive_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM drives WHERE id = ?", (drive_id,))


def mark_drive_scanned(drive_id: int, item_count: int) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE drives
            SET last_scanned_at = ?, item_count = ?
            WHERE id = ?
            """,
            (utc_now(), item_count, drive_id),
        )


def update_drive_smart(drive_id: int, fields: dict[str, Any]) -> None:
    """Persist SMART health fields from report_to_storage()."""
    with db() as conn:
        conn.execute(
            """
            UPDATE drives SET
                smart_status = ?,
                smart_status_raw = ?,
                smart_temperature_c = ?,
                smart_model = ?,
                smart_serial = ?,
                smart_media = ?,
                smart_bus = ?,
                hardware_type = ?,
                hardware_label = ?,
                smart_source = ?,
                smart_detail = ?,
                smart_json = ?,
                smart_checked_at = ?,
                sector_attrs_available = ?,
                sector_reallocated = ?,
                sector_pending = ?,
                sector_uncorrectable = ?,
                sector_crc = ?,
                sector_reported_uncorrect = ?,
                nvme_media_errors = ?,
                sector_summary = ?,
                volume_label = ?,
                capacity_total_bytes = COALESCE(?, capacity_total_bytes),
                capacity_free_bytes = COALESCE(?, capacity_free_bytes),
                capacity_used_bytes = COALESCE(?, capacity_used_bytes),
                capacity_checked_at = CASE WHEN ? IS NOT NULL THEN ? ELSE capacity_checked_at END
            WHERE id = ?
            """,
            (
                fields.get("smart_status") or "",
                fields.get("smart_status_raw") or "",
                fields.get("smart_temperature_c"),
                fields.get("smart_model") or "",
                fields.get("smart_serial") or "",
                fields.get("smart_media") or "",
                fields.get("smart_bus") or "",
                fields.get("hardware_type") or "",
                fields.get("hardware_label") or "",
                fields.get("smart_source") or "",
                fields.get("smart_detail") or "",
                fields.get("smart_json") or "",
                utc_now(),
                int(fields.get("sector_attrs_available") or 0),
                fields.get("sector_reallocated"),
                fields.get("sector_pending"),
                fields.get("sector_uncorrectable"),
                fields.get("sector_crc"),
                fields.get("sector_reported_uncorrect"),
                fields.get("nvme_media_errors"),
                fields.get("sector_summary") or "",
                fields.get("volume_label") or "",
                fields.get("capacity_total_bytes"),
                fields.get("capacity_free_bytes"),
                fields.get("capacity_used_bytes"),
                fields.get("capacity_total_bytes"),
                utc_now() if fields.get("capacity_total_bytes") is not None else None,
                drive_id,
            ),
        )


def update_drive_capacity(
    drive_id: int,
    total_bytes: int | None,
    free_bytes: int | None,
    used_bytes: int | None = None,
) -> None:
    """Store volume capacity (size + free space)."""
    if total_bytes is None and free_bytes is None:
        return
    if used_bytes is None and total_bytes is not None and free_bytes is not None:
        used_bytes = max(0, int(total_bytes) - int(free_bytes))
    with db() as conn:
        conn.execute(
            """
            UPDATE drives SET
                capacity_total_bytes = ?,
                capacity_free_bytes = ?,
                capacity_used_bytes = ?,
                capacity_checked_at = ?
            WHERE id = ?
            """,
            (
                total_bytes,
                free_bytes,
                used_bytes,
                utc_now(),
                drive_id,
            ),
        )


def apply_smart_drive_tag(drive_id: int, status: str) -> str:
    """
    Replace any existing SMART:* drive tags with the current health tag.
    Returns the tag name applied.
    """
    from smart_health import SMART_TAG_PREFIX, smart_tag_for

    tag_name = smart_tag_for(status)
    existing = get_drive_tags(drive_id)
    kept = [t for t in existing if not t.upper().startswith(SMART_TAG_PREFIX.upper())]
    kept.append(tag_name)
    set_drive_tags(drive_id, kept)
    return tag_name


# --- Media items ---


def upsert_media_items(drive_id: int, items: list[dict[str, Any]]) -> int:
    """Replace scan results for a drive: upsert found paths, remove gone ones."""
    now = utc_now()
    with db() as conn:
        existing = {
            row["file_path"]: row["id"]
            for row in conn.execute(
                "SELECT id, file_path FROM media_items WHERE drive_id = ?",
                (drive_id,),
            )
        }
        seen_paths: set[str] = set()

        for item in items:
            path = item["file_path"]
            seen_paths.add(path)
            if path in existing:
                conn.execute(
                    """
                    UPDATE media_items SET
                        relative_path = ?,
                        file_name = ?,
                        display_title = ?,
                        extension = ?,
                        size_bytes = ?,
                        parent_folder = ?,
                        kind = ?,
                        show_name = ?,
                        season = ?,
                        episode = ?,
                        last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        item["relative_path"],
                        item["file_name"],
                        item["display_title"],
                        item["extension"],
                        item["size_bytes"],
                        item["parent_folder"],
                        item["kind"],
                        item.get("show_name"),
                        item.get("season"),
                        item.get("episode"),
                        now,
                        existing[path],
                    ),
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
                    (
                        drive_id,
                        path,
                        item["relative_path"],
                        item["file_name"],
                        item["display_title"],
                        item["extension"],
                        item["size_bytes"],
                        item["parent_folder"],
                        item["kind"],
                        item.get("show_name"),
                        item.get("season"),
                        item.get("episode"),
                        now,
                        now,
                    ),
                )

        gone = set(existing.keys()) - seen_paths
        if gone:
            conn.executemany(
                "DELETE FROM media_items WHERE drive_id = ? AND file_path = ?",
                [(drive_id, p) for p in gone],
            )

        count = conn.execute(
            "SELECT COUNT(*) AS c FROM media_items WHERE drive_id = ?",
            (drive_id,),
        ).fetchone()["c"]

        conn.execute(
            """
            UPDATE drives
            SET last_scanned_at = ?, item_count = ?
            WHERE id = ?
            """,
            (now, count, drive_id),
        )
        return int(count)


def list_media(
    drive_id: int | None = None,
    q: str | None = None,
    tag: str | None = None,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT m.*, d.name AS drive_name,
               GROUP_CONCAT(t.name, ', ') AS tags
        FROM media_items m
        JOIN drives d ON d.id = m.drive_id
        LEFT JOIN media_tags mt ON mt.media_id = m.id
        LEFT JOIN tags t ON t.id = mt.tag_id
        WHERE 1=1
    """
    params: list[Any] = []

    if drive_id is not None:
        sql += " AND m.drive_id = ?"
        params.append(drive_id)
    if q:
        sql += " AND (m.display_title LIKE ? OR m.file_name LIKE ? OR m.relative_path LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    if kind:
        sql += " AND m.kind = ?"
        params.append(kind)
    if tag:
        sql += """
            AND m.id IN (
                SELECT mt2.media_id FROM media_tags mt2
                JOIN tags t2 ON t2.id = mt2.tag_id
                WHERE t2.name = ? COLLATE NOCASE
            )
        """
        params.append(tag)

    # Type first (movies → TV → audio → other), then natural title order
    sql += """
        GROUP BY m.id
        ORDER BY
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

    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def get_media(media_id: int) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            """
            SELECT m.*, d.name AS drive_name,
                   GROUP_CONCAT(t.name, ', ') AS tags
            FROM media_items m
            JOIN drives d ON d.id = m.drive_id
            LEFT JOIN media_tags mt ON mt.media_id = m.id
            LEFT JOIN tags t ON t.id = mt.tag_id
            WHERE m.id = ?
            GROUP BY m.id
            """,
            (media_id,),
        ).fetchone()
        return dict(row) if row else None


# --- Tags ---


def list_tags() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT t.*,
                   (SELECT COUNT(*) FROM media_tags mt WHERE mt.tag_id = t.id) AS media_count,
                   (SELECT COUNT(*) FROM drive_tags dt WHERE dt.tag_id = t.id) AS drive_count
            FROM tags t
            ORDER BY t.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]


def ensure_tag(name: str) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Tag name required")
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        return int(cur.lastrowid)


def set_media_tags(media_id: int, tag_names: list[str]) -> None:
    cleaned = [t.strip() for t in tag_names if t.strip()]
    with db() as conn:
        conn.execute("DELETE FROM media_tags WHERE media_id = ?", (media_id,))
        for name in cleaned:
            row = conn.execute(
                "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if row:
                tag_id = row["id"]
            else:
                cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
                tag_id = cur.lastrowid
            conn.execute(
                "INSERT OR IGNORE INTO media_tags (media_id, tag_id) VALUES (?, ?)",
                (media_id, tag_id),
            )


def add_media_tag(media_id: int, tag_name: str) -> None:
    tag_id = ensure_tag(tag_name)
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO media_tags (media_id, tag_id) VALUES (?, ?)",
            (media_id, tag_id),
        )


def remove_media_tag(media_id: int, tag_name: str) -> None:
    with db() as conn:
        conn.execute(
            """
            DELETE FROM media_tags
            WHERE media_id = ?
              AND tag_id = (
                  SELECT id FROM tags WHERE name = ? COLLATE NOCASE
              )
            """,
            (media_id, tag_name),
        )


def set_drive_tags(drive_id: int, tag_names: list[str]) -> None:
    cleaned = [t.strip() for t in tag_names if t.strip()]
    with db() as conn:
        conn.execute("DELETE FROM drive_tags WHERE drive_id = ?", (drive_id,))
        for name in cleaned:
            row = conn.execute(
                "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if row:
                tag_id = row["id"]
            else:
                cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
                tag_id = cur.lastrowid
            conn.execute(
                "INSERT OR IGNORE INTO drive_tags (drive_id, tag_id) VALUES (?, ?)",
                (drive_id, tag_id),
            )


def get_drive_tags(drive_id: int) -> list[str]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN drive_tags dt ON dt.tag_id = t.id
            WHERE dt.drive_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (drive_id,),
        ).fetchall()
        return [r["name"] for r in rows]


def get_media_tags(media_id: int) -> list[str]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN media_tags mt ON mt.tag_id = t.id
            WHERE mt.media_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (media_id,),
        ).fetchall()
        return [r["name"] for r in rows]
