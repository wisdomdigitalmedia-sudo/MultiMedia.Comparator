from __future__ import annotations

import unittest

from topology import recommend, subnet_hosts


class RecommendTests(unittest.TestCase):
    def test_linux_catalog_windows(self):
        plan = recommend(
            role="catalog",
            files_where="windows",
            this={"os": "linux", "lan_ip": "192.0.2.10", "agent_url": "http://192.0.2.10:8766"},
            peers=[],
        )
        self.assertEqual(plan["code"], "linux-catalog-windows")
        self.assertFalse(plan["needs_agent_here"])
        self.assertTrue(plan["needs_comparator_here"])

    def test_windows_files(self):
        plan = recommend(
            role="files",
            files_where="this",
            this={"os": "windows", "lan_ip": "192.0.2.20", "agent_url": "http://192.0.2.20:8766"},
        )
        self.assertTrue(plan["needs_agent_here"])
        self.assertFalse(plan["needs_comparator_here"])

    def test_subnet(self):
        hosts = subnet_hosts("192.0.2.20")
        self.assertNotIn("192.0.2.20", hosts)
        self.assertIn("192.0.2.1", hosts)


if __name__ == "__main__":
    unittest.main()
