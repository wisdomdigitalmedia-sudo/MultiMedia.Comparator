from __future__ import annotations

import io
import unittest
import zipfile

from mmc.config import BASE_DIR, find_catalog_db


class HostPackTests(unittest.TestCase):
    def test_installer_lives_in_this_repo(self):
        pack = BASE_DIR / "media-host" / "host-installer" / "pack.py"
        self.assertTrue(pack.is_file(), pack)

    def test_zip_builds_from_media_host(self):
        import sys

        pack_dir = str(BASE_DIR / "media-host" / "host-installer")
        if pack_dir not in sys.path:
            sys.path.insert(0, pack_dir)
        from pack import build_zip_bytes

        raw = build_zip_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
        self.assertIn("agent.py", names)
        self.assertIn("INSTALL.bat", names)
        self.assertIn("host-installer/wizard.py", names)
        self.assertIn("host-installer/topology.py", names)

    def test_catalog_search_includes_bundled_and_legacy(self):
        found = find_catalog_db()
        # May be None on a fresh clone; if present it must be a real file.
        if found is not None:
            self.assertTrue(found.is_file())
        bundled = BASE_DIR / "media-host" / "data"
        self.assertTrue(bundled.is_dir())


if __name__ == "__main__":
    unittest.main()
