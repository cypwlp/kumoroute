import importlib.util
import tempfile
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
                {"name": "KumoRoute-win-x64-setup.exe", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.8.1/KumoRoute-win-x64-setup.exe", "size": 23_000_000},
                {"name": "KumoRoute-win-x64.zip", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.8.1/KumoRoute-win-x64.zip", "size": 30_000_000},
                {"name": "KumoRoute-macos-universal.dmg", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.8.1/KumoRoute-macos-universal.dmg", "size": 54_000_000},
                {"name": "KumoRoute-linux-x86_64.AppImage", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.8.1/KumoRoute-linux-x86_64.AppImage", "size": 108_000_000},
                {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/cypwlp/kumoroute/releases/download/v0.8.1/SHA256SUMS.txt", "size": 600},
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

    def test_portable_windows_build_prefers_zip(self):
        with mock.patch.object(app.platform, "system", return_value="Windows"):
            asset = app.Api._update_asset(self._release(), True)
        self.assertEqual(asset["filename"], "KumoRoute-win-x64.zip")

    def test_checksum_parser_and_url_validation(self):
        digest = "a" * 64
        self.assertEqual(app.parse_sha256sums(f"{digest}  KumoRoute-win-x64-setup.exe\n", "KumoRoute-win-x64-setup.exe"), digest)
        self.assertTrue(app.safe_update_url("https://github.com/cypwlp/kumoroute/releases/download/v0.8.1/file.exe"))
        self.assertFalse(app.safe_update_url("https://evil.example/file.exe"))
        self.assertFalse(app.safe_update_url("http://github.com/file.exe"))

    def test_update_ui_has_install_action_and_checksum_argument(self):
        ui = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="btn-install-update"', html)
        self.assertIn('api("start_update_download", asset.download_url, asset.filename, asset.sha256_url', ui)
        self.assertIn('run_update_installer', ui)

    def test_windows_installer_updates_in_place_without_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            downloads = root / "Downloads"
            downloads.mkdir()
            installer = downloads / "KumoRoute-win-x64-setup.exe"
            installer.write_bytes(b"setup")
            api = app.Api.__new__(app.Api)
            with mock.patch.object(app.Path, "home", return_value=root), \
                 mock.patch.object(app, "data_dir", return_value=root / "appdata"), \
                 mock.patch.object(app.platform, "system", return_value="Windows"), \
                 mock.patch.object(api, "_create_update_backup", return_value={"ok": True}), \
                 mock.patch.object(app.subprocess, "Popen") as popen, \
                 mock.patch.object(app.threading, "Thread") as thread:
                result = api.run_update_installer(str(installer), "0.8.1")
        self.assertTrue(result["ok"], result)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], [str(installer), "/P", "/UPDATE", "/R"])
        thread.assert_called_once()

    def test_update_prompt_is_shown_once_per_version(self):
        ui = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        for element_id in ("update-modal", "btn-update-later", "btn-update-view", "btn-update-now"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("lastUpdatePromptVersion", ui)
        self.assertIn("prefs.lastUpdatePromptVersion === latest", ui)
        self.assertIn("maybeShowUpdatePrompt(res)", ui)
        self.assertIn('id="btn-update-later"', html)
        self.assertIn("downloadAndInstallUpdate", ui)
        self.assertIn("start_update_download", ui)
        self.assertIn("update_download_status", ui)
        self.assertIn("cancel_update_download", ui)
        self.assertIn('id="update-progress"', html)
        self.assertIn('id="update-backup-panel"', html)
        self.assertIn('id="update-modal-progress"', html)
        self.assertIn("targetVersion", ui)
        self.assertIn('id="subscription-update-hours"', html)
        self.assertIn('id="btn-export-backup"', html)
        self.assertIn('id="btn-import-backup"', html)


    def test_portable_marker_and_signing_prep_are_wired(self):
        pack = (ROOT / "packaging" / "pack.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        signing_doc = (ROOT / "SIGNING.md").read_text(encoding="utf-8")
        self.assertIn("KumoRoute.portable", pack)
        self.assertIn("WINDOWS_CERTIFICATE_BASE64", workflow)
        self.assertIn("prepare_windows_signing.ps1", workflow)
        self.assertIn("verify_windows_signature.ps1", workflow)
        self.assertIn("certificateThumbprint", signing_doc)

    def test_update_backup_state_tracks_previous_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "app"
            app_dir.mkdir()
            exe = app_dir / "KumoRoute.exe"
            exe.write_bytes(b"old")
            (app_dir / "core").mkdir()
            (app_dir / "core" / "mihomo.exe").write_bytes(b"core")
            api = app.Api.__new__(app.Api)
            api._current_app_paths = lambda: (exe, app_dir)
            with mock.patch.object(app, "data_dir", return_value=root / "data"):
                state = api._create_update_backup("99.0.0")
                info = api.get_update_state()
            self.assertEqual(state["from_version"], app.APP_VERSION)
            self.assertTrue((root / "data" / "updates" / "previous" / "KumoRoute.exe").is_file())
            self.assertTrue(info["backup_available"])
            self.assertTrue(info["failed"])

if __name__ == "__main__":
    unittest.main()
