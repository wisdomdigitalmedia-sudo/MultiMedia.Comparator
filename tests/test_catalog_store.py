from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from mmc.catalog_store import (
    add_drive,
    delete_drive,
    ensure_catalog,
    fold_by_depth,
    get_drive,
    list_media,
    max_folder_depth,
    normalize_windows_path,
    upsert_media_items,
)


class PathNormalizeTests(unittest.TestCase):
    def test_letters(self):
        self.assertEqual(normalize_windows_path("h"), "H:/")
        self.assertEqual(normalize_windows_path("K:"), "K:/")
        self.assertEqual(normalize_windows_path("d:\\Movies"), "D:/Movies")


class CatalogWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self._tmp())
        self.db = self.tmp / "catalog.db"
        ensure_catalog(self.db)

    def _tmp(self) -> str:
        import tempfile

        self._ctx = tempfile.TemporaryDirectory()
        return self._ctx.name

    def tearDown(self):
        self._ctx.cleanup()

    def test_add_delete_drive(self):
        drive_id = add_drive("CapTest", str(self.tmp), source_type="local", catalog_path=self.db)
        row = get_drive(drive_id, self.db)
        self.assertEqual(row["name"], "CapTest")
        removed = delete_drive(drive_id, self.db)
        self.assertEqual(removed["name"], "CapTest")
        self.assertIsNone(get_drive(drive_id, self.db))

    def test_upsert_and_cascade(self):
        drive_id = add_drive("Lib", str(self.tmp), source_type="local", catalog_path=self.db)
        count = upsert_media_items(
            drive_id,
            [
                {
                    "file_path": "/tmp/a.mkv",
                    "relative_path": "a.mkv",
                    "file_name": "a.mkv",
                    "display_title": "A",
                    "extension": ".mkv",
                    "size_bytes": 10,
                    "parent_folder": "",
                    "kind": "movie",
                }
            ],
            catalog_path=self.db,
        )
        self.assertEqual(count, 1)
        conn = sqlite3.connect(self.db)
        n = conn.execute("SELECT COUNT(*) FROM media_items").fetchone()[0]
        conn.close()
        self.assertEqual(n, 1)
        delete_drive(drive_id, self.db)
        conn = sqlite3.connect(self.db)
        n = conn.execute("SELECT COUNT(*) FROM media_items").fetchone()[0]
        conn.close()
        self.assertEqual(n, 0)

    def test_list_media_filters_and_pages(self):
        drive_id = add_drive("Lib", str(self.tmp), source_type="local", catalog_path=self.db)
        upsert_media_items(
            drive_id,
            [
                {
                    "file_path": "/tmp/a.mkv",
                    "relative_path": "Movies/a.mkv",
                    "file_name": "a.mkv",
                    "display_title": "Alpha",
                    "extension": ".mkv",
                    "size_bytes": 10,
                    "parent_folder": "Movies",
                    "kind": "movie",
                },
                {
                    "file_path": "/tmp/b.mp3",
                    "relative_path": "Music/b.mp3",
                    "file_name": "b.mp3",
                    "display_title": "Beta",
                    "extension": ".mp3",
                    "size_bytes": 5,
                    "parent_folder": "Music",
                    "kind": "audio",
                },
            ],
            catalog_path=self.db,
        )
        rows, total = list_media(drive_id, catalog_path=self.db)
        self.assertEqual(total, 2)
        self.assertEqual(len(rows), 2)
        movies, movie_total = list_media(drive_id, kind="movie", catalog_path=self.db)
        self.assertEqual(movie_total, 1)
        self.assertEqual(movies[0]["display_title"], "Alpha")
        page, page_total = list_media(drive_id, limit=1, offset=0, catalog_path=self.db)
        self.assertEqual(page_total, 2)
        self.assertEqual(len(page), 1)


class FoldDepthTests(unittest.TestCase):
    def _track(self, rel, size=1):
        name = rel.rsplit("/", 1)[-1]
        return {
            "relative_path": rel,
            "file_name": name,
            "display_title": name,
            "size_bytes": size,
            "kind": "audio",
            "extension": ".mp3",
        }

    def test_album_depth_hides_tracks(self):
        items = [
            self._track("Music/Dylan/Freewheelin/01.mp3", 10),
            self._track("Music/Dylan/Freewheelin/02.mp3", 20),
            self._track("Music/Dylan/Blonde/01.mp3", 30),
            self._track("Movies/Dune.mkv", 40),
        ]
        items[-1]["kind"] = "movie"
        items[-1]["extension"] = ".mkv"
        self.assertEqual(max_folder_depth(items), 3)
        albums = fold_by_depth(items, 3)
        folders = [r for r in albums if r.get("is_folder")]
        files = [r for r in albums if not r.get("is_folder")]
        self.assertEqual(len(folders), 2)
        self.assertEqual({f["display_title"] for f in folders}, {"Freewheelin", "Blonde"})
        self.assertEqual(sum(f["file_count"] for f in folders), 3)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["file_name"], "Dune.mkv")

    def test_zero_depth_lists_files(self):
        items = [self._track("Music/A/B/c.mp3")]
        rows = fold_by_depth(items, 0)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_folder"])

    def test_prefix_drill_in(self):
        items = [
            self._track("Music/Dylan/Freewheelin/01.mp3"),
            self._track("Music/Dylan/Freewheelin/02.mp3"),
        ]
        rows = fold_by_depth(items, 3, prefix="Music/Dylan/Freewheelin")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not r["is_folder"] for r in rows))


if __name__ == "__main__":
    unittest.main()
