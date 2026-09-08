from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from mmc.capacity import (
    fill_unknown_drive_capacities,
    index_agent_drives,
    needs_capacity,
)
from mmc.catalog_import import list_catalog_drives, update_catalog_capacity


def _make_catalog(path: Path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE drives (
            id INTEGER PRIMARY KEY,
            name TEXT,
            root_path TEXT,
            item_count INTEGER DEFAULT 0,
            source_type TEXT DEFAULT 'local',
            agent_url TEXT DEFAULT '',
            agent_token TEXT DEFAULT '',
            capacity_total_bytes INTEGER,
            capacity_free_bytes INTEGER,
            capacity_used_bytes INTEGER,
            capacity_checked_at TEXT,
            hardware_type TEXT,
            hardware_label TEXT,
            smart_status TEXT,
            volume_label TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO drives (
            id, name, root_path, item_count, source_type, agent_url,
            capacity_total_bytes, capacity_free_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


class IndexAgentDrivesTests(unittest.TestCase):
    def test_maps_letter_and_skips_empty_total(self):
        mapped = index_agent_drives(
            [
                {
                    "letter": "K:",
                    "total_bytes": 1000,
                    "free_bytes": 250,
                    "used_bytes": 750,
                },
                {"letter": "H:", "total_bytes": 0, "free_bytes": 0},
                {"path": "M:/", "size_bytes": 2000, "free_bytes": 500},
            ]
        )
        self.assertEqual(mapped["K"]["total_bytes"], 1000)
        self.assertEqual(mapped["K"]["free_bytes"], 250)
        self.assertEqual(mapped["M"]["used_bytes"], 1500)
        self.assertNotIn("H", mapped)

    def test_maps_linux_mount_path(self):
        mapped = index_agent_drives(
            [
                {
                    "letter": "/mnt/media",
                    "path": "/mnt/media",
                    "total_bytes": 4000,
                    "free_bytes": 1000,
                    "used_bytes": 3000,
                }
            ]
        )
        self.assertEqual(mapped["/mnt/media"]["total_bytes"], 4000)
        self.assertNotIn("/", mapped)

    def test_needs_capacity(self):
        self.assertTrue(needs_capacity({"capacity_total_bytes": 0}))
        self.assertTrue(needs_capacity({}))
        self.assertFalse(needs_capacity({"capacity_total_bytes": 800}))


class FillUnknownTests(unittest.TestCase):
    def setUp(self):
        import mmc.capacity as cap

        cap._LAST_REMOTE_FAIL_AT = 0.0

    def test_remote_letters_written_not_invented(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "catalog.db"
            _make_catalog(
                db,
                [
                    (7, "External H", "H:/", 4207, "remote", "http://192.0.2.20:8766", None, None),
                    (9, "External J", "J:/", 8193, "remote", "http://192.0.2.20:8766", None, None),
                    (3, "External D", "D:/", 3980, "remote", "http://192.0.2.20:8766", 8000, 40),
                ],
            )
            agent_rows = [
                {"letter": "H:", "total_bytes": 8_000_000_000_000, "free_bytes": 100, "used_bytes": 7_999_999_999_900},
                {"letter": "J:", "total_bytes": 0, "free_bytes": 0},
            ]
            with patch("mmc.capacity.list_agent_drives", return_value=agent_rows):
                summary = fill_unknown_drive_capacities(
                    str(db), local=False, remote=True
                )
            self.assertEqual(summary["filled"], 1)
            drives = {d["name"]: d for d in list_catalog_drives(str(db))}
            self.assertEqual(drives["External H"]["capacity_total_bytes"], 8_000_000_000_000)
            self.assertIsNone(drives["External J"]["capacity_total_bytes"])
            self.assertEqual(drives["External D"]["capacity_total_bytes"], 8000)

    def test_remote_linux_path_written(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "catalog.db"
            _make_catalog(
                db,
                [
                    (2, "NAS media", "/mnt/media", 12, "remote", "http://192.0.2.40:8766", None, None),
                ],
            )
            agent_rows = [
                {
                    "letter": "/mnt/media",
                    "path": "/mnt/media",
                    "total_bytes": 5000,
                    "free_bytes": 2000,
                    "used_bytes": 3000,
                }
            ]
            with patch("mmc.capacity.list_agent_drives", return_value=agent_rows):
                summary = fill_unknown_drive_capacities(
                    str(db), local=False, remote=True
                )
            self.assertEqual(summary["filled"], 1)
            row = list_catalog_drives(str(db))[0]
            self.assertEqual(row["capacity_total_bytes"], 5000)

    def test_local_path_filled_from_disk_usage(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "catalog.db"
            _make_catalog(
                db,
                [
                    (1, "Root", "/", 0, "local", "", None, None),
                ],
            )
            summary = fill_unknown_drive_capacities(str(db), local=True, remote=False)
            self.assertEqual(summary["filled"], 1)
            row = list_catalog_drives(str(db))[0]
            self.assertTrue(row["capacity_total_bytes"] and row["capacity_total_bytes"] > 0)

    def test_update_rejects_empty(self):
        self.assertFalse(update_catalog_capacity(1, None, None))


if __name__ == "__main__":
    unittest.main()
