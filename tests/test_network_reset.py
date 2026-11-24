import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "client" / "ui"


class NetworkResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (UI / "index.html").read_text(encoding="utf-8")
        cls.app = (UI / "app.js").read_text(encoding="utf-8")
        cls.i18n = (UI / "i18n.js").read_text(encoding="utf-8")
        cls.tauri = (ROOT / "tauri" / "src" / "commands.rs").read_text(encoding="utf-8")
        cls.main = (ROOT / "tauri" / "src" / "main.rs").read_text(encoding="utf-8")
        cls.python = (ROOT / "client" / "app.py").read_text(encoding="utf-8")
        cls.caps = (ROOT / "tauri" / "capabilities" / "main.json").read_text(encoding="utf-8")
        cls.build_rs = (ROOT / "tauri" / "build.rs").read_text(encoding="utf-8")

    def test_ui_exposes_reset_button_and_confirmation(self):
        self.assertIn('id="btn-reset-network"', self.index)
        self.assertIn("一鍵重置網路", self.index)
        self.assertIn('$("#btn-reset-network").addEventListener("click"', self.app)
        self.assertIn("function resetNetwork(", self.app)
        # A destructive action must ask first.
        self.assertIn("confirm(", self.app.split("function resetNetwork(")[1].split("async function repairNetwork")[0])

    def test_frontend_wires_the_command_for_tauri_and_demo(self):
        self.assertIn("reset_network: [],", self.app)
        self.assertIn('case "reset_network"', self.app)
        self.assertIn('api("reset_network")', self.app)

    def test_backends_implement_the_reset(self):
        self.assertIn("commands::reset_network", self.main)
        self.assertIn("pub fn reset_network(state: State<'_, Shared>) -> Value", self.tauri)
        self.assertIn("fn reset_settings_defaults(", self.tauri)
        self.assertIn("def reset_network(self) -> dict:", self.python)
        for needle in ('"auto"', "force_disable_ipv6", "vpn_proxy_pending", '"coexist"'):
            self.assertIn(needle, self.tauri)

    def test_reset_only_touches_our_own_proxy_changes(self):
        section = self.tauri.split("pub fn reset_network")[1].split("pub fn vpn_forget_credentials")[0]
        self.assertIn("proxy::is_on", section)
        self.assertIn("proxy::set_system_proxy", section)
        self.assertIn("proxy::recover_stale_proxy", section)
        self.assertNotIn("apply(0, \"\"", section)

    def test_tauri_acl_allows_every_registered_command(self):
        """Tauri v2 rejects unlisted commands with "not allowed by ACL"."""
        import json

        caps = json.loads(self.caps)
        allowed = {
            item[len("allow-") :].replace("-", "_")
            for item in caps["permissions"]
            if item.startswith("allow-")
        }
        block = self.main.split("generate_handler![", 1)[1].split("])", 1)[0]
        commands = [part.split("::")[-1].strip() for part in block.split(",") if part.strip()]
        self.assertIn("reset_network", commands)
        self.assertEqual([c for c in commands if c not in allowed], [])

        # tauri/build.rs declares the app manifest for codegen; a missing entry
        # breaks the build (or, worse, the ACL at runtime).
        manifest = self.build_rs.split("const COMMANDS: &[&str] = &[", 1)[1].split("];", 1)[0]
        declared = {part.strip().strip('",') for part in manifest.splitlines() if part.strip()}
        self.assertEqual([c for c in commands if c not in declared], [])

    def test_translations_cover_the_reset_flow(self):
        for text in ("一鍵重置網路", "重置中…", "網路已重置", "部分步驟未完成"):
            self.assertIn(f'"{text}"', self.i18n)


if __name__ == "__main__":
    unittest.main()


class ReconcileAndEgressTests(unittest.TestCase):
    """Startup reconcile, egress readout and the relogin warning."""

    @classmethod
    def setUpClass(cls):
        cls.app = (UI / "app.js").read_text(encoding="utf-8")
        cls.index = (UI / "index.html").read_text(encoding="utf-8")
        cls.i18n = (UI / "i18n.js").read_text(encoding="utf-8")
        cls.rs = (ROOT / "tauri" / "src" / "commands.rs").read_text(encoding="utf-8")
        cls.proxy_rs = (ROOT / "tauri" / "src" / "proxy.rs").read_text(encoding="utf-8")
        cls.main = (ROOT / "tauri" / "src" / "main.rs").read_text(encoding="utf-8")
        cls.python = (ROOT / "client" / "app.py").read_text(encoding="utf-8")

    def test_reconcile_runs_at_startup_and_on_demand(self):
        self.assertIn("pub fn reconcile_network", self.rs)
        self.assertIn("pub fn reconcile_now", self.rs)
        self.assertIn("reconcile_now(&mut s)", self.main)
        self.assertIn('id="btn-reconcile"', self.index)
        self.assertIn('$("#btn-reconcile").addEventListener', self.app)
        self.assertIn("reconcileNetwork(true)", self.app)

    def test_vpn_mode_turns_the_proxy_off(self):
        section = self.rs.split("fn apply_network_mode")[1].split("pub fn reconcile_now")[0]
        self.assertIn('"vpn" =>', section)
        self.assertIn("proxy::disable_verified", section)
        self.assertIn("any_proxy_on", self.proxy_rs)

    def test_disable_is_verified_and_reports_relogin(self):
        self.assertIn("pub fn disable_verified", self.proxy_rs)
        self.assertIn("needs_relogin", self.rs)
        self.assertIn("需要重新登入", self.rs)
        self.assertIn("needs_relogin", self.python)

    def test_egress_readout_is_wired(self):
        self.assertIn("pub fn detect_egress", self.rs)
        self.assertIn('id="egress-line"', self.index)
        self.assertIn("function refreshEgress", self.app)
        for label in ("經系統代理", "經 VPN", "直接連線"):
            self.assertIn(f'"{label}"', self.i18n)
        self.assertIn("def detect_egress", self.python)

    def test_relogin_banner_locale_strings_exist(self):
        self.assertIn('id="proxy-banner"', self.index)
        self.assertIn("Windows 仍在保留系統代理設定", self.i18n)
