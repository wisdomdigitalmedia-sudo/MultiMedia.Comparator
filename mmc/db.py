"""SQLite store for comparator sources, probes, and last compare run."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from mmc.config import DATA_DIR, DATABASE_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL, -- folder | catalog
                root_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_scanned_at TEXT,
                item_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                display_title TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                kind TEXT DEFAULT 'movie',
                show_name TEXT,
                season INTEGER,
                episode INTEGER,
                identity_key TEXT,
                identity_label TEXT,
                edition TEXT,
                drive_name TEXT DEFAULT '',
                catalog_id INTEGER,
                extra_json TEXT DEFAULT '',
                UNIQUE(source_id, file_path),
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS probes (
                file_path TEXT PRIMARY KEY,
                ok INTEGER NOT NULL,
                tool TEXT DEFAULT '',
                error TEXT DEFAULT '',
                probed_at TEXT NOT NULL,
                duration_s REAL,
                width INTEGER,
                height INTEGER,
                video_codec TEXT,
                audio_codec TEXT,
                hdr TEXT,
                bit_rate INTEGER,
                result_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_items_identity ON items(identity_key);
            CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);
            """
        )


def add_source(name: str, kind: str, root_path: str) -> int:
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM sources WHERE kind = ? AND root_path = ?",
            (kind, root_path),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE sources SET name = ? WHERE id = ?",
                (name, existing["id"]),
            )
            return int(existing["id"])
        cur = conn.execute(
            """
            INSERT INTO sources (name, kind, root_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, kind, root_path, utc_now()),
        )
        return int(cur.lastrowid)


def list_sources() -> list[dict[str, Any]]:
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY id").fetchall()]


def delete_source(source_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


def delete_items_by_path(file_path: str) -> int:
    raw = (file_path or "").strip()
    if not raw:
        return 0
    variants = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}
    with db() as conn:
        placeholders = ",".join("?" * len(variants))
        cur = conn.execute(
            f"DELETE FROM items WHERE file_path IN ({placeholders})",
            tuple(variants),
        )
        return int(cur.rowcount or 0)


def replace_source_items(source_id: int, items: list[dict[str, Any]]) -> int:
    now = utc_now()
    with db() as conn:
        conn.execute("DELETE FROM items WHERE source_id = ?", (source_id,))
        for item in items:
            extra = {
                k: item.get(k)
                for k in ("agent_url", "agent_token", "source_type", "drive_root", "drive_id")
                if item.get(k) not in (None, "")
            }
            conn.execute(
                """
                INSERT INTO items (
                    source_id, file_path, relative_path, file_name, display_title,
                    extension, size_bytes, kind, show_name, season, episode,
                    identity_key, identity_label, edition, drive_name, catalog_id, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    item.get("file_path") or "",
                    item.get("relative_path") or "",
                    item.get("file_name") or "",
                    item.get("display_title") or item.get("identity_label") or "",
                    item.get("extension") or "",
                    int(item.get("size_bytes") or 0),
                    item.get("kind") or "movie",
                    item.get("show_name"),
                    item.get("season"),
                    item.get("episode"),
                    item.get("identity_key"),
                    item.get("identity_label"),
                    item.get("edition"),
                    item.get("drive_name") or item.get("source_name") or "",
                    item.get("catalog_id"),
                    json.dumps(extra) if extra else "",
                ),
            )
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM items WHERE source_id = ?", (source_id,)
        ).fetchone()["c"]
        conn.execute(
            "UPDATE sources SET last_scanned_at = ?, item_count = ? WHERE id = ?",
            (now, count, source_id),
        )
        return int(count)


def library_counts() -> dict[str, Any]:
    """Cheap source + kind totals — do not load every media row."""
    with db() as conn:
        sources = [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY id").fetchall()]
        kinds = {
            (row["kind"] or "other"): int(row["c"])
            for row in conn.execute(
                "SELECT kind, COUNT(*) AS c FROM items GROUP BY kind"
            )
        }
        total = int(
            conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
        )
    return {"sources": sources, "item_count": total, "kinds": kinds}


def load_all_items() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM items").fetchall()
        out = []
        for r in rows:
            item = dict(r)
            extra = {}
            if item.get("extra_json"):
                try:
                    extra = json.loads(item["extra_json"])
                except json.JSONDecodeError:
                    extra = {}
            item.update(extra)
            out.append(item)
        return out


def save_probe(file_path: str, result: dict[str, Any]) -> None:
    video = result.get("video") or {}
    audio = result.get("audio") or {}
    with db() as conn:
        conn.execute(
            """
            INSERT INTO probes (
                file_path, ok, tool, error, probed_at, duration_s,
                width, height, video_codec, audio_codec, hdr, bit_rate, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                ok = excluded.ok,
                tool = excluded.tool,
                error = excluded.error,
                probed_at = excluded.probed_at,
                duration_s = excluded.duration_s,
                width = excluded.width,
                height = excluded.height,
                video_codec = excluded.video_codec,
                audio_codec = excluded.audio_codec,
                hdr = excluded.hdr,
                bit_rate = excluded.bit_rate,
                result_json = excluded.result_json
            """,
            (
                file_path,
                1 if result.get("ok") else 0,
                result.get("tool") or "",
                result.get("error") or "",
                utc_now(),
                result.get("duration_s"),
                (video or {}).get("width"),
                (video or {}).get("height"),
                (video or {}).get("codec_name"),
                (audio or {}).get("codec_name"),
                result.get("hdr"),
                result.get("bit_rate"),
                json.dumps(result),
            ),
        )


def load_probes(paths: list[str] | None = None) -> dict[str, dict[str, Any]]:
    with db() as conn:
        if paths:
            out: dict[str, dict[str, Any]] = {}
            chunk = 400
            for i in range(0, len(paths), chunk):
                part = paths[i : i + chunk]
                q = ",".join("?" * len(part))
                rows = conn.execute(
                    f"SELECT file_path, result_json FROM probes WHERE file_path IN ({q})",
                    part,
                ).fetchall()
                for r in rows:
                    try:
                        out[r["file_path"]] = json.loads(r["result_json"])
                    except json.JSONDecodeError:
                        continue
            return out
        rows = conn.execute("SELECT file_path, result_json FROM probes").fetchall()
        out = {}
        for r in rows:
            try:
                out[r["file_path"]] = json.loads(r["result_json"])
            except json.JSONDecodeError:
                continue
        return out


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def get_setting(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default
