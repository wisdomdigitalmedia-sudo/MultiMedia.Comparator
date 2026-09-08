from __future__ import annotations

import unittest

from mmc.codecs import audio_rank, resolve_audio, resolve_video, video_rank
from mmc.config import AUDIO_EXTENSIONS, MEDIA_EXTENSIONS, VIDEO_EXTENSIONS


class CodecResolveTests(unittest.TestCase):
    def test_video_aliases(self):
        self.assertEqual(resolve_video("hevc").family, "hevc")
        self.assertEqual(resolve_video("x265").family, "hevc")
        self.assertEqual(resolve_video("h.264").family, "h264")
        self.assertEqual(resolve_video("avc1").family, "h264")
        self.assertEqual(resolve_video("av01").family, "av1")
        self.assertEqual(resolve_video("xvid").family, "xvid")
        self.assertGreater(video_rank("av1"), video_rank("h264"))
        self.assertGreater(video_rank("hevc"), video_rank("mpeg4"))

    def test_audio_aliases_and_atmos(self):
        self.assertEqual(resolve_audio("truehd").family, "truehd")
        self.assertEqual(resolve_audio("truehd", atmos=True).family, "truehd_atmos")
        self.assertEqual(resolve_audio("dca").family, "dts")
        self.assertGreater(audio_rank("flac"), audio_rank("mp3"))
        self.assertGreater(audio_rank("truehd", atmos=True), audio_rank("ac3"))

    def test_extension_coverage(self):
        for ext in (".mkv", ".mp4", ".avi", ".m2ts", ".webm", ".ts", ".mov", ".wmv"):
            self.assertIn(ext, VIDEO_EXTENSIONS)
        for ext in (".flac", ".mp3", ".m4a", ".opus", ".dts", ".ac3", ".thd"):
            self.assertIn(ext, AUDIO_EXTENSIONS)
        self.assertTrue(MEDIA_EXTENSIONS >= VIDEO_EXTENSIONS)
        self.assertNotIn(".nfo", MEDIA_EXTENSIONS)
        self.assertNotIn(".iso", MEDIA_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
