from __future__ import annotations

import unittest

from mmc.dashboard import enrich_drive, free_pct, space_tone, used_pct


class SpaceMathTests(unittest.TestCase):
    def test_free_pct(self):
        self.assertAlmostEqual(free_pct(1000, 250) or 0, 25.0)
        self.assertIsNone(free_pct(0, 10))
        self.assertIsNone(free_pct(None, 10))

    def test_used_from_free(self):
        self.assertAlmostEqual(used_pct(1000, None, 200) or 0, 80.0)

    def test_tone(self):
        self.assertEqual(space_tone(None), "unknown")
        self.assertEqual(space_tone(25), "ok")
        self.assertEqual(space_tone(8), "warn")
        self.assertEqual(space_tone(4), "critical")
        self.assertEqual(space_tone(2), "critical")


class EnrichDriveTests(unittest.TestCase):
    def test_known_drive(self):
        card = enrich_drive(
            {
                "id": 3,
                "name": "External D",
                "root_path": "D:/",
                "item_count": 3980,
                "capacity_total_bytes": 1000,
                "capacity_free_bytes": 40,
                "capacity_used_bytes": 960,
                "hardware_type": "portable_hdd",
                "smart_status": "healthy",
            }
        )
        self.assertTrue(card["capacity_known"])
        self.assertEqual(card["letter"], "D")
        self.assertEqual(card["tone"], "critical")
        self.assertAlmostEqual(card["free_pct"], 4.0)

    def test_unknown_not_zeroed(self):
        card = enrich_drive(
            {
                "name": "External K",
                "root_path": "K:/",
                "item_count": 12,
                "capacity_total_bytes": 0,
                "capacity_free_bytes": 0,
            }
        )
        self.assertFalse(card["capacity_known"])
        self.assertIsNone(card["free_pct"])
        self.assertEqual(card["tone"], "unknown")
        self.assertEqual(card["free_label"], "—")


if __name__ == "__main__":
    unittest.main()
