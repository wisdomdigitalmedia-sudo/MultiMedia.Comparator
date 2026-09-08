from __future__ import annotations

import unittest
from pathlib import Path

from deps import _firewall_rule_present, host_status
from pack import build_zip_bytes


class HostStatusTests(unittest.TestCase):
    def test_status_has_os_and_steps(self):
        st = host_status()
        self.assertIn(st["os"], {"Linux", "Windows", "Darwin"})
        self.assertIn("ffprobe", st)
        self.assertIn("smart", st)
        self.assertIn("agent", st)
        self.assertTrue(st["python"]["ok"])
        self.assertEqual(st["port"], 8766)
        self.assertTrue(st["lan_ip"])


class PackTests(unittest.TestCase):
    def test_zip_contains_click_and_run(self):
        raw = build_zip_bytes()
        self.assertGreater(len(raw), 1000)
        import zipfile, io

        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            start = zf.read("START_HERE.txt").decode("utf-8", errors="replace")
        self.assertIn("INSTALL.bat", names)
        self.assertIn("INSTALL.sh", names)
        self.assertIn("agent.py", names)
        self.assertIn("host-installer/wizard.py", names)
        self.assertIn("host-installer/topology.py", names)
        self.assertIn("host-installer/templates/wizard.html", names)
        self.assertIn("START_HERE.txt", names)
        self.assertIn("v1.6", start)
        self.assertIn("OPEN_FIREWALL.bat", names)
        self.assertIn("host-installer/open-firewall.ps1", names)


class FirewallParseTests(unittest.TestCase):
    def test_missing_rule(self):
        self.assertFalse(_firewall_rule_present("No rules match the specified criteria.", 1))

    def test_present_rule(self):
        self.assertTrue(
            _firewall_rule_present(
                "Rule Name:                            Media Catalog Agent\nLocalPort:                            8766\n",
                0,
            )
        )


if __name__ == "__main__":
    unittest.main()
