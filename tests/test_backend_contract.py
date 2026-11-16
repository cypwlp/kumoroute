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
        for method in [
            "vpn_list", "vpn_add", "vpn_edit", "vpn_delete", "vpn_forget_credentials",
            "vpn_set_auto_proxy", "vpn_set_restore_proxy", "set_network_mode",
            "network_diagnostics", "network_repair", "test_node_delay",
            "start_update_download", "update_download_status", "cancel_update_download",
            "get_update_state", "rollback_update", "set_subscription_auto_update",
            "subscription_auto_update", "export_backup", "import_backup",
        ]:
            self.assertRegex(py, rf"def {re.escape(method)}\(")
            self.assertRegex(rs, rf"pub fn {re.escape(method)}\(")
        for method in [
            "vpn_add", "vpn_edit", "vpn_delete", "vpn_forget_credentials", "vpn_set_auto_proxy",
            "vpn_set_restore_proxy", "set_network_mode", "network_diagnostics",
            "network_repair", "test_node_delay",
            "start_update_download", "update_download_status", "cancel_update_download",
            "get_update_state", "rollback_update", "set_subscription_auto_update",
            "subscription_auto_update", "export_backup", "import_backup",
        ]:
            self.assertIn(f"{method}:", js)

    def test_connection_reliability_and_backup_are_wired(self):
        py = (ROOT / "client" / "app.py").read_text(encoding="utf-8")
        backup = (ROOT / "client" / "backup_support.py").read_text(encoding="utf-8")
        rs = (ROOT / "tauri" / "src" / "commands.rs").read_text(encoding="utf-8")
        js = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        spec = (ROOT / "KumoRoute.spec").read_text(encoding="utf-8")
        site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn("_probe_http", py)
        self.assertIn("fn probe_http", rs)
        self.assertIn("_vpn_validate_connection", py)
        self.assertIn("vpn_validation_should_rollback", rs)
        self.assertIn("dns_leak_confirmed", py)
        self.assertIn("dns_leak_confirmed", rs)
        self.assertIn("dns_leak_confirmed", js)
        self.assertIn("dns_resolver_ip", js)
        self.assertIn("proxy_egress_ip", js)
        self.assertIn("validation", js)
        self.assertIn("previous_entries", py)
        self.assertIn("previous_entries", rs)
        self.assertIn("api_cls.export_backup = export_backup", backup)
        self.assertIn("api_cls.import_backup = import_backup", backup)
        self.assertIn("backup_support", spec)
        self.assertIn('id="subscription-update-hours"', html)
        self.assertIn('id="btn-update-all-subscriptions"', html)
        self.assertIn('id="btn-import-backup"', html)
        self.assertIn("Verified + rollback", site)
        self.assertIn("Measured, not guessed", site)

    def test_ipv6_and_ui_optimizations_are_wired(self):
        py = (ROOT / "client" / "app.py").read_text(encoding="utf-8")
        rs = (ROOT / "tauri" / "src" / "state.rs").read_text(encoding="utf-8")
        commands_rs = (ROOT / "tauri" / "src" / "commands.rs").read_text(encoding="utf-8")
        js = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("_has_global_ipv6", py)
        self.assertIn("ipv6_route_available", rs)
        self.assertIn("data-retest-node", js)
        self.assertIn("proxyNodeLimit", js)
        self.assertIn('id="log-search"', html)
        self.assertIn('id="vpn-profile-modal"', html)
        self.assertIn('id="toggle-vpn-restore-proxy"', html)
        self.assertIn('id="network-diagnostics-result"', html)
        self.assertIn("dot_templates", py)
        self.assertIn("dot_templates", commands_rs)
        site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        site_app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        self.assertIn('class="feature-grid"', site)
        self.assertIn('class="download-grid"', site)
        self.assertIn('id="download-bottom"', site)
        self.assertIn('querySelectorAll(`[data-dl=', site_app)


if __name__ == "__main__":
    unittest.main()
