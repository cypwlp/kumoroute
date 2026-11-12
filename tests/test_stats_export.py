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
