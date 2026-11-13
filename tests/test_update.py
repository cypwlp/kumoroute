import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_update", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class UpdateAssetTests(unittest.TestCase):
    def _release(self):
        return {
            "assets": [
                {"name": "KumoRoute-win-x64-setup.exe", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.6.1/KumoRoute-win-x64-setup.exe", "size": 23_000_000},
                {"name": "KumoRoute-win-x64.zip", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.6.1/KumoRoute-win-x64.zip", "size": 30_000_000},
                {"name": "KumoRoute-macos-universal.dmg", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.6.1/KumoRoute-macos-universal.dmg", "size": 54_000_000},
                {"name": "KumoRoute-linux-x86_64.AppImage", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.6.1/KumoRoute-linux-x86_64.AppImage", "size": 108_000_000},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.6.1/SHA256SUMS.txt", "size": 600},
            ]
        }

    def test_windows_prefers_setup_over_zip(self):
        with mock.patch.object(app.platform, "system", return_value="Windows"):
            asset = app.Api._update_asset(self._release())
        self.assertEqual(asset["filename"], "KumoRoute-win-x64-setup.exe")
        self.assertTrue(asset["sha256_url"].endswith("SHA256SUMS.txt"))

    def test_platform_asset_selection(self):
        with mock.patch.object(app.platform, "system", return_value="Darwin"):
            self.assertEqual(app.Api._update_asset(self._release())["filename"], "KumoRoute-macos-universal.dmg")
        with mock.patch.object(app.platform, "system", return_value="Linux"):
            self.assertEqual(app.Api._update_asset(self._release())["filename"], "KumoRoute-linux-x86_64.AppImage")

    def test_checksum_parser_and_url_validation(self):
        digest = "a" * 64
        self.assertEqual(app.parse_sha256sums(f"{digest}  KumoRoute-win-x64-setup.exe\n", "KumoRoute-win-x64-setup.exe"), digest)
        self.assertTrue(app.safe_update_url("https://github.com/cypwlp/kumoroute/releases/download/v0.6.1/file.exe"))
        self.assertFalse(app.safe_update_url("https://evil.example/file.exe"))
        self.assertFalse(app.safe_update_url("http://github.com/file.exe"))

    def test_update_ui_has_install_action_and_checksum_argument(self):
        ui = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="btn-install-update"', html)
        self.assertIn('api("install_update", asset.download_url, asset.filename, asset.sha256_url', ui)
        self.assertIn('run_update_installer', ui)


if __name__ == "__main__":
    unittest.main()
