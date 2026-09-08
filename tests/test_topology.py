from __future__ import annotations

import unittest

from mmc.topology import recommend, subnet_hosts, this_os


class SubnetTests(unittest.TestCase):
    def test_slash_24_skips_self(self):
        hosts = subnet_hosts("192.168.1.50")
        self.assertEqual(len(hosts), 253)
        self.assertNotIn("192.168.1.50", hosts)
        self.assertIn("192.168.1.1", hosts)
        self.assertIn("192.168.1.254", hosts)

    def test_bad_ip(self):
        self.assertEqual(subnet_hosts("not-an-ip"), [])


class RecommendMatrixTests(unittest.TestCase):
    def _plan(self, os_id: str, role: str, files_where: str, peers=None):
        this = {
            "os": os_id,
            "os_label": os_id,
            "lan_ip": "192.0.2.10",
            "agent_url": "http://192.0.2.10:8766",
            "hostname": "test-pc",
        }
        return recommend(role=role, files_where=files_where, this=this, peers=peers or [])

    def test_linux_catalog_windows_server(self):
        plan = self._plan("linux", "catalog", "windows")
        self.assertEqual(plan["code"], "linux-catalog-windows")
        self.assertIn("Windows file server", plan["title"])
        self.assertFalse(plan["needs_agent_here"])
        self.assertTrue(plan["needs_comparator_here"])
        self.assertTrue(any("INSTALL.bat" in step for step in plan["other_machine"]))
        self.assertTrue(any("8766" in step for step in plan["then"]))

    def test_linux_to_linux(self):
        plan = self._plan("linux", "catalog", "linux")
        self.assertIn("Linux media server", plan["title"])
        self.assertTrue(any("INSTALL.sh" in step for step in plan["other_machine"]))

    def test_windows_to_windows_split(self):
        plan = self._plan("windows", "catalog", "windows")
        self.assertIn("Windows catalog + Windows file server", plan["title"])
        self.assertTrue(any("run.bat" in step for step in plan["this_machine"]))
        self.assertTrue(any("INSTALL.bat" in step for step in plan["other_machine"]))

    def test_windows_to_linux(self):
        plan = self._plan("windows", "catalog", "linux")
        self.assertIn("Linux media server", plan["title"])
        self.assertTrue(any("INSTALL.sh" in step for step in plan["other_machine"]))

    def test_windows_file_host(self):
        plan = self._plan("windows", "files", "this")
        self.assertTrue(plan["needs_agent_here"])
        self.assertFalse(plan["needs_comparator_here"])
        self.assertIn("http://192.0.2.10:8766", " ".join(plan["this_machine"]))

    def test_single_machine(self):
        plan = self._plan("linux", "both", "this")
        self.assertIn("Single Linux machine", plan["title"])
        self.assertFalse(plan["other_machine"])
        self.assertFalse(plan["needs_agent_here"])
        self.assertIn("No second computer", " ".join(plan["this_machine"]))

    def test_mac_catalog_windows(self):
        plan = self._plan("mac", "catalog", "windows")
        self.assertIn("Mac catalog + Windows file server", plan["title"])

    def test_mixed(self):
        plan = self._plan("linux", "catalog", "mixed")
        self.assertGreaterEqual(len(plan["other_machine"]), 2)

    def test_suggests_found_windows_agent(self):
        peers = [
            {
                "ip": "192.0.2.20",
                "agent": True,
                "catalog": False,
                "agent_url": "http://192.0.2.20:8766",
                "agent_os": "windows",
                "hostname": "MEDIA-PC",
            }
        ]
        plan = self._plan("linux", "catalog", "windows", peers=peers)
        self.assertEqual(plan["suggested_agent"], "http://192.0.2.20:8766")
        self.assertIn("192.0.2.20:8766", " ".join(plan["then"]))

    def test_ignores_this_machine_peer(self):
        peers = [
            {
                "ip": "192.0.2.10",
                "agent": True,
                "this_machine": True,
                "agent_url": "http://192.0.2.10:8766",
                "agent_os": "linux",
            }
        ]
        plan = self._plan("linux", "catalog", "linux", peers=peers)
        self.assertEqual(plan["suggested_agent"], "")

    def test_this_os_is_known(self):
        self.assertIn(this_os(), {"linux", "windows", "mac"})


if __name__ == "__main__":
    unittest.main()
