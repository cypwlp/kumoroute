import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_reliability", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ReliabilityTests(unittest.TestCase):
    def test_profile_update_rolls_back_on_reload_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = app.Store(root / "settings.json", app.DEFAULT_SETTINGS)
            profiles = app.Profiles(store, root / "profiles")
            source = root / "source.yaml"
            source.write_text("mode: rule\nproxies: []\n", encoding="utf-8")
            entry = profiles.add_local(str(source))
            entry["kind"] = "remote"
            entry["url"] = "https://example.com/sub"
            previous = dict(entry)
            profiles._apply_remote_text(entry["id"], "mode: global\nproxies: []\n")
            self.assertIn("mode: global", profiles.path_of(entry["id"]).read_text())
            profiles.rollback_to(entry["id"], previous)
            self.assertEqual(
                profiles.path_of(entry["id"]).read_text(),
                "mode: rule\nproxies: []\n",
            )
            self.assertEqual(profiles.get(entry["id"])["updated_at"], previous["updated_at"])

    def test_invalid_profile_update_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = app.Store(root / "settings.json", app.DEFAULT_SETTINGS)
            profiles = app.Profiles(store, root / "profiles")
            source = root / "source.yaml"
            source.write_text("mode: rule\nproxies: []\n", encoding="utf-8")
            entry = profiles.add_local(str(source))
            entry["kind"] = "remote"
            entry["url"] = "https://example.com/sub"
            before = profiles.path_of(entry["id"]).read_text()
            with self.assertRaises(ValueError):
                profiles._apply_remote_text(entry["id"], "mode: [broken")
            self.assertEqual(profiles.path_of(entry["id"]).read_text(), before)

    def test_diagnostic_preview_redacts_urls_ips_and_secrets(self):
        raw = (
            "GET https://example.com/sub?token=secret --> 127.0.0.1:9090 "
            "203.0.113.7 2001:db8::1 Authorization: Bearer abc.def token=plain"
        )
        safe, summary = app._sanitize_diagnostics_report(raw)
        for value in ("https://example.com/sub?token=secret", "127.0.0.1:9090", "203.0.113.7", "2001:db8::1", "abc.def", "token=plain"):
            self.assertNotIn(value, safe)
        self.assertGreaterEqual(summary["urls"], 1)
        self.assertGreaterEqual(summary["ips"], 2)
        self.assertGreaterEqual(summary["secrets"], 2)

    def test_remote_url_validation_rejects_credentials(self):
        with self.assertRaises(ValueError):
            app.Profiles._validate_remote_url("https://user:pass@example.com/sub")
        with self.assertRaises(ValueError):
            app.Profiles._validate_remote_url("ftp://example.com/sub")

    def test_stale_proxy_restores_only_our_loopback_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = app.Store(root / "settings.json", app.DEFAULT_SETTINGS)
            store.data["mixed_port"] = 7890
            store.data["original_proxy"] = {"enable": 1, "server": "10.0.0.2:8080", "override": "local"}
            with mock.patch.object(app.sys, "platform", "win32"), \
                 mock.patch.object(app, "get_system_proxy", return_value={"enable": 1, "server": "127.0.0.1:7890", "override": ""}), \
                 mock.patch.object(app, "_apply_registry_proxy") as apply_proxy:
                result = app.recover_stale_proxy(store)
            self.assertTrue(result["restored"])
            apply_proxy.assert_called_once_with(1, "10.0.0.2:8080", "local")
            self.assertIsNone(store.data["original_proxy"])

    def test_stale_proxy_does_not_overwrite_external_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = app.Store(root / "settings.json", app.DEFAULT_SETTINGS)
            store.data["original_proxy"] = {"enable": 0, "server": "", "override": ""}
            with mock.patch.object(app.sys, "platform", "win32"), \
                 mock.patch.object(app, "get_system_proxy", return_value={"enable": 1, "server": "10.0.0.2:8080", "override": ""}), \
                 mock.patch.object(app, "_apply_registry_proxy") as apply_proxy:
                result = app.recover_stale_proxy(store)
            self.assertTrue(result["cleared_stale"])
            apply_proxy.assert_not_called()
            self.assertIsNone(store.data["original_proxy"])


if __name__ == "__main__":
    unittest.main()