import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "client" / "ui"


class UiPersonalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (UI / "index.html").read_text(encoding="utf-8")
        cls.app = (UI / "app.js").read_text(encoding="utf-8")
        cls.i18n = (UI / "i18n.js").read_text(encoding="utf-8")
        cls.theme_boot = (UI / "theme-boot.js").read_text(encoding="utf-8")
        cls.css = (UI / "style.css").read_text(encoding="utf-8")

    def test_theme_boot_runs_before_styles_and_i18n_before_app(self):
        self.assertLess(self.index.index("theme-boot.js"), self.index.index("style.css"))
        self.assertLess(self.index.index("i18n.js"), self.index.index("app.js"))

    def test_settings_expose_theme_and_language_choices(self):
        for value in ("system", "dark", "light"):
            self.assertIn(f'id="select-theme"', self.index)
            self.assertIn(f'<option value="{value}">', self.index)
        for value in ("system", "zh-Hant", "zh-Hans", "en"):
            self.assertIn('id="select-language"', self.index)
            self.assertIn(f'<option value="{value}">', self.index)

    def test_preferences_validate_and_persist_personalization(self):
        self.assertIn("kumoroute.preferences.v1", self.app)
        self.assertIn('theme: "system", language: "system"', self.app)
        self.assertIn('["system", "dark", "light"].includes(parsed.theme)', self.app)
        self.assertIn('["system", "zh-Hant", "zh-Hans", "en"].includes(parsed.language)', self.app)
        self.assertIn('$("#select-theme").addEventListener("change"', self.app)
        self.assertIn('$("#select-language").addEventListener("change"', self.app)

    def test_system_theme_reads_preference_before_css(self):
        self.assertIn("localStorage.getItem", self.theme_boot)
        self.assertIn("document.documentElement.dataset.theme", self.theme_boot)
        self.assertIn('@media (prefers-color-scheme: light)', self.css)
        self.assertIn(':root[data-theme="light"]', self.css)
        self.assertIn(':root[data-theme="system"]', self.css)

    def test_translation_engine_tracks_original_strings_for_round_trips(self):
        self.assertIn("const originals = new WeakMap()", self.i18n)
        self.assertIn("originals.get(node)", self.i18n)
        self.assertIn("const value = translate(source)", self.i18n)
        self.assertIn('target === "zh-Hans"', self.i18n)
        self.assertIn('"Traditional Chinese"', self.i18n)
        self.assertIn('"Simplified Chinese"', self.i18n)
        self.assertIn('"Theme"', self.i18n)
        self.assertIn('"Language"', self.i18n)
        self.assertIn('["连接埠", "端口"]', self.i18n)
        self.assertIn('["软体", "软件"]', self.i18n)

    def test_user_owned_names_are_excluded_from_translation(self):
        protected_markers = [
            'id="cur-profile" data-no-i18n',
            'id="logbox" class="logbox" data-no-i18n',
            'id="diagnostics-preview" class="diagnostics-preview" tabindex="0" data-no-i18n',
            '<span data-no-i18n>${esc(p.name)}</span>',
            'class="health-node" data-no-i18n',
            '<h2 data-no-i18n>${esc(group.name)}</h2>',
            '<strong data-no-i18n>${esc(effective)}</strong>',
            '<b data-no-i18n>${esc(now)}</b>',
            'class="attr-name" data-no-i18n',
            'title="${esc(node.name)}" data-no-i18n-attrs',
            'title="${esc(event.detail || "")}" data-no-i18n-attrs',
        ]
        for marker in protected_markers:
            self.assertIn(marker, self.index + self.app)

    def test_major_pages_have_english_translations(self):
        required = [
            "一鍵接管系統流量，規則、全局、直連自由切換。",
            "只記錄 KumoRoute 開啟期間的流量；資料保存在本機，不會上傳。",
            "每次測速會保留最近 10 次結果；依成功率、平均延遲與波動推薦較穩定節點。",
            "先看上方目前出口，再從左側策略組選擇；測速使用",
            "支援 Clash / mihomo YAML 訂閱連結，或匯入本機配置文件。",
            "mihomo 核心輸出（最近 300 行）。",
            "連接埠修改後會自動重啟核心。",
            "選擇介面主題與顯示語言；切換會立即生效。",
        ]
        for source in required:
            self.assertRegex(self.i18n, re.escape(source) + r'"\s*:\s*"')

    def test_english_audit_assets_are_wired_into_ci(self):
        workflow = (ROOT / ".github" / "workflows" / "smoke.yml").read_text(encoding="utf-8")
        self.assertIn("node --check client/ui/i18n.js", workflow)
        self.assertIn("node --check client/ui/theme-boot.js", workflow)


if __name__ == "__main__":
    unittest.main()
