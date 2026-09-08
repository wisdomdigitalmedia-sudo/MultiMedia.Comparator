from __future__ import annotations

import unittest
from types import SimpleNamespace

from mmc.file_delete import drop_copy_from_groups, find_copy
from mmc.grouper import DuplicateGroup, ScoredCopy
from mmc.identity import Identity
from mmc.quality import QualityScore


def _copy(path: str, rank: int, keep: bool, score: float = 80.0) -> ScoredCopy:
    ident = Identity(kind="movie", key="k", label="Film", title="Film")
    qs = QualityScore(total=score, summary="ok")
    return ScoredCopy(
        item={"file_path": path, "file_name": path.rsplit("/", 1)[-1], "size_bytes": 10},
        identity=ident,
        score=qs,
        rank=rank,
        is_winner=keep,
    )


class FindCopyTests(unittest.TestCase):
    def test_slash_normalize(self):
        g = DuplicateGroup(
            key="k",
            kind="movie",
            label="Film",
            copies=[_copy("E:/Movies/a.mkv", 1, True), _copy("S:/Movies/a.mkv", 2, False)],
        )
        found = find_copy([g], "S:/Movies/a.mkv")
        self.assertIsNotNone(found)
        self.assertEqual(found[1].item["file_path"], "S:/Movies/a.mkv")
        self.assertIsNone(find_copy([g], "D:/nope.mkv"))


class DropCopyTests(unittest.TestCase):
    def test_group_removed_when_one_left(self):
        g = DuplicateGroup(
            key="k",
            kind="movie",
            label="Film",
            copies=[_copy("E:/a.mkv", 1, True), _copy("S:/a.mkv", 2, False)],
            score_gap=10,
        )
        out = drop_copy_from_groups([g], "S:/a.mkv")
        self.assertEqual(out, [])

    def test_keep_reassigned(self):
        g = DuplicateGroup(
            key="k",
            kind="movie",
            label="Film",
            copies=[
                _copy("E:/best.mkv", 1, True, 90),
                _copy("F:/mid.mkv", 2, False, 70),
                _copy("S:/low.mkv", 3, False, 40),
            ],
            score_gap=20,
        )
        out = drop_copy_from_groups([g], "E:/best.mkv")
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0].copies), 2)
        winner = next(c for c in out[0].copies if c.is_winner)
        self.assertEqual(winner.item["file_path"], "F:/mid.mkv")


if __name__ == "__main__":
    unittest.main()
