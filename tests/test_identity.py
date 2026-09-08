"""Identity keys against real Entertainment.Servers-style release names."""

from __future__ import annotations

import unittest

from mmc.grouper import group_items
from mmc.identity import episode_identity, identify, movie_identity, normalize_title


def item(name: str, kind: str = "movie", **extra):
    return {
        "file_name": name,
        "relative_path": extra.pop("relative_path", f"Movies/{name}"),
        "file_path": extra.pop("file_path", f"E:/Movies/{name}"),
        "display_title": extra.pop("display_title", name),
        "extension": "." + name.rsplit(".", 1)[-1],
        "size_bytes": extra.pop("size_bytes", 8_000_000_000),
        "kind": kind,
        **extra,
    }


class TitleNormalizeTests(unittest.TestCase):
    def test_articles_and_spelling(self):
        self.assertEqual(normalize_title("The Terminator"), "terminator")
        self.assertEqual(
            normalize_title("Terminator 2 - Judgement Day"),
            "terminator 2 judgment day",
        )
        self.assertEqual(normalize_title("John Wick Chapter 4"), "john wick 4")
        self.assertEqual(normalize_title("Dune Part One"), "dune part 1")
        self.assertEqual(normalize_title("Tango & Cash"), "tango and cash")


class MovieIdentityTests(unittest.TestCase):
    def test_matrix_variants_same_key(self):
        a = movie_identity("The.Matrix.1999.2160p.BluRay.REMUX.HDR10.HEVC.TrueHD.7.1.Atmos-UnKn0wn.mkv")
        b = movie_identity("The.Matrix.(1999).HDDVD.1080p.x264.DTS-McFly.mkv")
        self.assertEqual(a.key, b.key)
        self.assertEqual(a.year, 1999)
        self.assertIn("matrix", a.key)

    def test_sequels_stay_apart(self):
        a = movie_identity("The.Matrix.Reloaded.2003.720p.BluRay.x264-CtrlHD.mkv")
        b = movie_identity("The.Matrix.Revolutions.2003.REMASTERED.1080p.BluRay.X264-AMIABLE.mkv")
        c = movie_identity("The.Matrix.1999.2160p.BluRay.REMUX.HDR10.HEVC.TrueHD.7.1.Atmos-UnKn0wn.mkv")
        self.assertNotEqual(a.key, b.key)
        self.assertNotEqual(a.key, c.key)
        self.assertNotEqual(b.key, c.key)

    def test_scene_prefix_stripped(self):
        a = movie_identity("veto-john.wick.chapter.4.2023.repack.1080p.bluray.x264.mkv")
        b = movie_identity("John.Wick.Chapter.4.2023.1080p.WEB-DL.DDP5.1.Atmos.H.264-WDYM.mkv")
        c = movie_identity("john.wick.chapter.4.2023.multi.hdr.2160p.web.h265-lost.mkv")
        self.assertEqual(a.key, b.key)
        self.assertEqual(b.key, c.key)

    def test_top_gun_not_maverick(self):
        a = movie_identity("Top Gun.mp4")
        b = movie_identity("Top.Gun.Maverick.2022.1080p.BluRay.x264-REEDNFO.mkv")
        self.assertNotEqual(a.key, b.key)

    def test_alien_franchise_not_merged(self):
        keys = {
            movie_identity("Alien.1979.DC.1080p.BluRay.X265-KARNAGE.mkv").key,
            movie_identity("Aliens.1986.Directors.Cut.iNTERNAL.CRF.1080p.BluRay.x264-MOOVEE.mkv").key,
            movie_identity("Alien.3.1992.720p.BluRay.x264-MELiTE.mkv").key,
            movie_identity("Alien.Covenant.2017.1080p.BluRay.x264-KARNAGE.mkv").key,
            movie_identity("Cowboys.And.Aliens.2011.EXTENDED.720p.BluRay.x264-CROSSBOW.mkv").key,
        }
        self.assertEqual(len(keys), 5)

    def test_edition_captured(self):
        ident = movie_identity(
            "Aliens.1986.Directors.Cut.iNTERNAL.CRF.1080p.BluRay.x264-MOOVEE{edition-Director's Cut}.mkv"
        )
        self.assertEqual(ident.year, 1986)
        self.assertTrue(ident.edition)
        self.assertIn("Director", ident.edition)

    def test_cd_parts_not_grouped(self):
        a = movie_identity("Kill.Bill.Vol.1.2003.CD1.1080p.BluRay.x264.mkv")
        b = movie_identity("Kill.Bill.Vol.1.2003.CD2.1080p.BluRay.x264.mkv")
        self.assertNotEqual(a.key, b.key)

    def test_hyphen_scene_names_stay_unique(self):
        a = movie_identity("creep-bloodgames1080.mkv")
        b = movie_identity("creep-thepunisherextended1080.mkv")
        c = movie_identity("sprinter-harlan2008.avi")
        self.assertNotEqual(a.key, b.key)
        self.assertNotIn("creep", a.key)
        self.assertIn("bloodgames", a.key)
        self.assertNotEqual(c.key, a.key)

    def test_title_after_year_kept(self):
        a = movie_identity("Abbott and Costello - 1941 - Hold That Ghost.avi")
        b = movie_identity("Abbott and Costello - 1941 - Keep 'Em Flying.avi")
        self.assertNotEqual(a.key, b.key)
        self.assertIn("hold that ghost", a.key)
        self.assertIn("keep em flying", b.key)

    def test_serial_chapters_stay_apart(self):
        a = movie_identity(
            "Oregon Trail (1939) Xvid - Western Serial - Chapter 02 of 15 - The Flaming Forest.avi"
        )
        b = movie_identity(
            "Oregon Trail (1939) Xvid - Western Serial - Chapter 03 of 15 - The Brink of Disaster.avi"
        )
        self.assertNotEqual(a.key, b.key)
        self.assertEqual(a.year, 1939)


class EpisodeIdentityTests(unittest.TestCase):
    def test_sxxexx(self):
        ident = episode_identity(
            "Band.Of.Brothers.S01E01.iNTERNAL.1080p.BluRay.x264-TENEIGHTY.mkv",
            "TV Shows\\Band.of.Brothers\\Band.Of.Brothers.S01E01.iNTERNAL.1080p.BluRay.x264-TENEIGHTY.mkv",
        )
        self.assertEqual(ident.season, 1)
        self.assertEqual(ident.episode, 1)
        self.assertIn("band of brothers", ident.key)

    def test_dated_daily(self):
        ident = episode_identity(
            "Jeopardy.2020.01.13.720p.HDTV.x264-NTb.mkv",
            "TV Shows\\Jeopardy\\Jeopardy.2020.01.13.720p.HDTV.x264-NTb.mkv",
        )
        self.assertEqual(ident.air_date, "2020-01-13")
        self.assertIn("date|2020-01-13", ident.key)

    def test_bare_e01(self):
        ident = episode_identity(
            "generation.war.e01.bdrip.x264-ffndvd.mkv",
            "TV Shows\\Generation.War\\generation.war.e01.bdrip.x264-ffndvd.mkv",
        )
        self.assertEqual(ident.episode, 1)

    def test_sxx_dot_exx(self):
        a = episode_identity(
            "South.Park.S07.E01 - I'm A Little Bit Country.avi",
            "TV Shows/South Park/South.Park.S07.E01 - I'm A Little Bit Country.avi",
        )
        b = episode_identity(
            "South.Park.S01E01.720p.BluRay.X264-REWARD.mkv",
            "TV Shows/South Park/South.Park.S01E01.720p.BluRay.X264-REWARD.mkv",
        )
        self.assertEqual(a.season, 7)
        self.assertEqual(a.episode, 1)
        self.assertNotEqual(a.key, b.key)

    def test_anime_bracket_group(self):
        a = episode_identity("[HorribleSubs] One Piece - 851 [1080p].mkv")
        b = episode_identity("[HorribleSubs] One Piece - 841 [1080p].mkv")
        self.assertIn("one piece", a.key)
        self.assertEqual(a.episode, 851)
        self.assertNotEqual(a.key, b.key)

    def test_secrets_not_truncated(self):
        ident = episode_identity(
            "Secrets.of.the.Whales.S01E01.Orca.Dynasty.1080p.DSNP.WEB-DL.DDP5.1.H.264-WH4L3S.mkv",
            "TV Shows/Secrets.of.the.Whales/Secrets.of.the.Whales.S01E01.Orca.Dynasty.1080p.mkv",
        )
        self.assertIn("secrets of the whales", ident.key)
        self.assertNotIn("|secre|", ident.key)


class GroupingTests(unittest.TestCase):
    def test_dune_part_one_merges_with_dune_2021(self):
        items = [
            item("Dune.2021.1080p.HDRip.X264.AC3-EVO.mkv", size_bytes=2_000_000_000),
            item("Dune.Part.One.2021.3D.1080p.BluRay.x264-PussyFoot.mkv", size_bytes=9_000_000_000),
            item("cebray-dune.part.one.2021.2160p.bluray.x265.mkv", size_bytes=25_000_000_000),
            item("Dune.1984.REMASTERED.1080p.BluRay.x264-NUDE.mkv", size_bytes=12_000_000_000),
        ]
        groups = group_items(items)
        keys_2021 = [g for g in groups if "2021" in g.key]
        keys_1984 = [g for g in groups if "1984" in g.key]
        self.assertEqual(len(keys_2021), 1)
        self.assertEqual(len(keys_2021[0].copies), 3)
        self.assertEqual(len(keys_1984), 0)  # single copy, not a duplicate group

    def test_winner_is_uhd_remux_not_webrip(self):
        items = [
            item(
                "The.Matrix.Reloaded.2003.720p.BluRay.x264-CtrlHD.mkv",
                size_bytes=4_000_000_000,
            ),
            item(
                "The.Matrix.Reloaded.2003.REMASTERED.1080p.BluRay.X264-AMIABLE.mkv",
                size_bytes=10_000_000_000,
            ),
            item(
                "The.Matrix.Reloaded.2003.2160p.BluRay.REMUX.HDR10.HEVC.TrueHD.7.1.Atmos-UnKn0wn.mkv",
                size_bytes=55_000_000_000,
            ),
        ]
        groups = group_items(items)
        self.assertEqual(len(groups), 1)
        winner = groups[0].winner
        assert winner is not None
        self.assertIn("2160p", winner.item["file_name"])
        self.assertIn("REMUX", winner.item["file_name"])
        self.assertGreater(winner.score.total, groups[0].extras[0].score.total)

    def test_same_show_name_different_years_split(self):
        items = [
            item(
                "In.The.Dark.2019.S01E01.Pilot.1080p.AMZN.WEB-DL.mkv",
                kind="episode",
                relative_path="TV Shows/In.The.Dark/In.The.Dark.2019.S01E01.Pilot.1080p.AMZN.WEB-DL.mkv",
                size_bytes=2_000_000_000,
            ),
            item(
                "In The Dark 2017 S01E01 720p WEB-DL HEVC x265 BONE.mkv",
                kind="episode",
                relative_path="TV Shows/In The Dark 2017/In The Dark 2017 S01E01 720p WEB-DL HEVC x265 BONE.mkv",
                size_bytes=400_000_000,
            ),
        ]
        groups = group_items(items)
        self.assertEqual(len(groups), 0)  # one file each after year split

        items.append(
            item(
                "In.The.Dark.2019.S01E01.Pilot.720p.AMZN.WEB-DL.mkv",
                kind="episode",
                relative_path="TV Shows/In.The.Dark/In.The.Dark.2019.S01E01.Pilot.720p.AMZN.WEB-DL.mkv",
                size_bytes=800_000_000,
            )
        )
        groups = group_items(items)
        self.assertEqual(len(groups), 1)
        self.assertTrue(all("2019" in c.item["file_name"] for c in groups[0].copies))

    def test_tv_same_episode_different_rips(self):
        items = [
            item(
                "Brooklyn.Nine.Nine.S01E01.HDTV.x264-LOL.mp4",
                kind="episode",
                relative_path="TV Shows/Brooklyn.Nine-Nine/Brooklyn.Nine.Nine.S01E01.HDTV.x264-LOL.mp4",
                size_bytes=300_000_000,
            ),
            item(
                "Brooklyn.Nine-Nine.S01E01.1080p.BluRay.x265-GROUP.mkv",
                kind="episode",
                relative_path="TV Shows/Brooklyn.Nine-Nine/Brooklyn.Nine-Nine.S01E01.1080p.BluRay.x265-GROUP.mkv",
                size_bytes=1_500_000_000,
            ),
        ]
        groups = group_items(items)
        self.assertEqual(len(groups), 1)
        winner = groups[0].winner
        assert winner is not None
        self.assertIn("1080p", winner.item["file_name"])

    def test_identify_uses_filename_not_dump_folder(self):
        ident = identify(
            item(
                "Avatar.2009.2160p.BluRay.HDR10.10bit.x265.HEVC.TrueHD.Atmos.7.1-PHOCiS.mkv",
                display_title="Drive E Backup",
                relative_path="Drive E Backup/Avatar.2009.2160p.BluRay.HDR10.10bit.x265.HEVC.TrueHD.Atmos.7.1-PHOCiS.mkv",
            )
        )
        self.assertIn("avatar", ident.key)
        self.assertEqual(ident.year, 2009)


if __name__ == "__main__":
    unittest.main()
