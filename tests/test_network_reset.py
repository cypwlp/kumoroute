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

    def test_translations_cover_the_reset_flow(self):
        for text in ("一鍵重置網路", "重置中…", "網路已重置", "部分步驟未完成"):
            self.assertIn(f'"{text}"', self.i18n)


if __name__ == "__main__":
    unittest.main()
