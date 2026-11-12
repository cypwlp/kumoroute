import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_export", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class StatsExportTests(unittest.TestCase):
    def _api(self):
        return app.Api.__new__(app.Api)

    def test_csv_export_has_bom_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(app.Path, "home", classmethod(lambda cls: root)):
                result = self._api().save_stats_export("csv", "date,download\n2026-11-12,1\n")
            self.assertTrue(result["ok"])
            path = Path(result["path"])
            self.assertTrue(path.is_file())
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertIn("date,download", path.read_text(encoding="utf-8-sig"))

    def test_diagnostics_sanitizer_redacts_sensitive_endpoints(self):
        raw = 'GET https://example.com/sub?token=secret --> www.example.com:443 192.168.1.2'
        safe = app._sanitize_diagnostics(raw)
        self.assertNotIn('token=secret', safe)
        self.assertNotIn('www.example.com:443', safe)
        self.assertNotIn('192.168.1.2', safe)
        self.assertIn('<redacted-url>', safe)
        self.assertIn('<redacted-endpoint>', safe)
        self.assertIn('<redacted-ip>', safe)

    def test_diagnostics_export_redacts_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir()
            (logs / "core.log").write_text("--> private.example:443 192.168.1.9\nhttps://example.com/sub?token=secret", encoding="utf-8")
            class FakeCore:
                def is_up(self):
                    return False
                def version(self):
                    return None
            class FakeProfiles:
                entries = []
                def active_entry(self):
                    return {"kind": "builtin"}
            class FakeStore:
                data = {"mode": "rule", "mixed_port": 7890, "controller_port": 9090}
            api = self._api()
            api._core = FakeCore()
            api._profiles = FakeProfiles()
            api._store = FakeStore()
            with mock.patch.object(app.Path, "home", classmethod(lambda cls: root)):
                with mock.patch.object(app, "data_dir", lambda: root):
                    result = api.export_diagnostics()
            self.assertTrue(result["ok"])
            text = Path(result["path"]).read_text(encoding="utf-8")
            self.assertIn("app_version: 0.4.0", text)
            self.assertIn("<redacted-url>", text)
            self.assertIn("<redacted-endpoint>", text)
            self.assertNotIn("token=secret", text)
            self.assertNotIn("private.example:443", text)

    def test_json_export_is_utf8_without_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(app.Path, "home", classmethod(lambda cls: root)):
                result = self._api().save_stats_export("json", '{"ok": true}')
            self.assertTrue(result["ok"])
            path = Path(result["path"])
            self.assertEqual(path.read_bytes(), b'{"ok": true}')


if __name__ == "__main__":
    unittest.main()
