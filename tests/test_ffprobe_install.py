from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from mmc.ffprobe_install import bundled_ffprobe, find_ffprobe


class FindFfprobeTests(unittest.TestCase):
    def test_prefers_path(self):
        with patch("mmc.ffprobe_install.shutil.which", return_value="/usr/bin/ffprobe"):
            self.assertEqual(find_ffprobe(), "/usr/bin/ffprobe")

    def test_falls_back_to_tools_dir(self):
        portable = bundled_ffprobe()

        def fake_which(_name):
            return None

        with patch("mmc.ffprobe_install.shutil.which", side_effect=fake_which):
            with patch("mmc.ffprobe_install.os.access", return_value=True):
                with patch.object(Path, "is_file", return_value=True):
                    found = find_ffprobe()
        self.assertEqual(found, str(portable))

    def test_missing_is_none(self):
        with patch("mmc.ffprobe_install.shutil.which", return_value=None):
            with patch.object(Path, "is_file", return_value=False):
                self.assertIsNone(find_ffprobe())


if __name__ == "__main__":
    unittest.main()
