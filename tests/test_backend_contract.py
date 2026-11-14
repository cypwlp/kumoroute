import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BackendContractTests(unittest.TestCase):
    def test_release_versions_are_consistent(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release.py"), "--check"],
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_vpn_and_proxy_commands_exist_in_both_backends(self):
        py = (ROOT / "client" / "app.py").read_text(encoding="utf-8")
        rs = (ROOT / "tauri" / "src" / "commands.rs").read_text(encoding="utf-8")
        js = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        for method in ["vpn_list", "vpn_add", "vpn_edit", "vpn_delete", "vpn_forget_credentials", "vpn_set_auto_proxy", "test_node_delay"]:
            self.assertRegex(py, rf"def {re.escape(method)}\(")
            self.assertRegex(rs, rf"pub fn {re.escape(method)}\(")
        for method in ["vpn_add", "vpn_edit", "vpn_delete", "vpn_forget_credentials", "vpn_set_auto_proxy", "test_node_delay"]:
            self.assertIn(f"{method}:", js)

    def test_ipv6_and_ui_optimizations_are_wired(self):
        py = (ROOT / "client" / "app.py").read_text(encoding="utf-8")
        rs = (ROOT / "tauri" / "src" / "state.rs").read_text(encoding="utf-8")
        js = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("_has_global_ipv6", py)
        self.assertIn("ipv6_route_available", rs)
        self.assertIn("data-retest-node", js)
        self.assertIn("proxyNodeLimit", js)
        self.assertIn('id="log-search"', html)
        self.assertIn('id="vpn-profile-modal"', html)


if __name__ == "__main__":
    unittest.main()
