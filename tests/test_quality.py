"""Quality ranking: remux / 4K / HDR / Atmos beat smaller rips."""

from __future__ import annotations

import unittest

from mmc.filename_meta import parse_filename_meta
from mmc.probe import ProbeResult, StreamInfo
from mmc.quality import score_item


class FilenameMetaTests(unittest.TestCase):
    def test_remux_uhd(self):
        meta = parse_filename_meta(
            "The.Matrix.1999.2160p.BluRay.REMUX.HDR10.HEVC.TrueHD.7.1.Atmos-UnKn0wn.mkv"
        )
        self.assertEqual(meta.height, 2160)
        self.assertEqual(meta.source, "remux")
        self.assertTrue(meta.remux)
        self.assertEqual(meta.video_codec, "hevc")
        self.assertEqual(meta.audio_codec, "truehd")
        self.assertTrue(meta.atmos)
        self.assertEqual(meta.hdr, "hdr10")
        self.assertEqual(meta.channels, 7.1)

    def test_webrip_1080(self):
        meta = parse_filename_meta("100.Girls.2000.1080p.WEBRip.DD5.1.x264-NTb.mkv")
        self.assertEqual(meta.height, 1080)
        self.assertEqual(meta.source, "webrip")
        self.assertEqual(meta.video_codec, "h264")
        self.assertEqual(meta.audio_codec, "ac3")


class ScoreTests(unittest.TestCase):
    def test_4k_remux_beats_720_bluray(self):
        hi = score_item(
            {
                "file_name": "Movie.1999.2160p.BluRay.REMUX.HDR10.HEVC.TrueHD.7.1.Atmos-GRP.mkv",
                "extension": ".mkv",
                "size_bytes": 50_000_000_000,
                "kind": "movie",
            }
        )
        lo = score_item(
            {
                "file_name": "Movie.1999.720p.BluRay.x264-GRP.mkv",
                "extension": ".mkv",
                "size_bytes": 4_000_000_000,
                "kind": "movie",
            }
        )
        self.assertGreater(hi.total, lo.total)

    def test_webdl_beats_cam(self):
        web = score_item(
            {
                "file_name": "Movie.2020.1080p.WEB-DL.H264.AC3-EVO.mkv",
                "extension": ".mkv",
                "size_bytes": 4_000_000_000,
                "kind": "movie",
            }
        )
        cam = score_item(
            {
                "file_name": "Movie.2020.CAM.XviD-EVO.avi",
                "extension": ".avi",
                "size_bytes": 700_000_000,
                "kind": "movie",
            }
        )
        self.assertGreater(web.total, cam.total)

    def test_probe_overrides_lying_filename(self):
        probe = ProbeResult(
            ok=True,
            tool="ffprobe",
            path="x.mkv",
            duration_s=7200,
            size_bytes=2_000_000_000,
            video=StreamInfo(codec_type="video", codec_name="mpeg4", width=720, height=480),
            audio=StreamInfo(codec_type="audio", codec_name="mp3", channels=2),
        )
        scored = score_item(
            {
                "file_name": "Movie.1999.2160p.BluRay.REMUX.mkv",
                "extension": ".mkv",
                "size_bytes": 2_000_000_000,
                "kind": "movie",
            },
            probe=probe,
        )
        self.assertEqual(scored.height, 480)
        self.assertTrue(scored.probed)
        self.assertEqual(scored.video_codec, "mpeg4")

    def test_3d_penalized(self):
        flat = score_item(
            {
                "file_name": "Avatar.2009.1080p.BluRay.X264-AMIABLE.mkv",
                "extension": ".mkv",
                "size_bytes": 12_000_000_000,
                "kind": "movie",
            }
        )
        stereo = score_item(
            {
                "file_name": "Avatar.3D.2009.H-SBS.H264.English.DTS.mkv",
                "extension": ".mkv",
                "size_bytes": 12_000_000_000,
                "kind": "movie",
            }
        )
        self.assertGreater(flat.total, stereo.total)
        self.assertTrue(stereo.is_3d)


if __name__ == "__main__":
    unittest.main()
