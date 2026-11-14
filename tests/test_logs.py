import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_logs", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class LogFilteringTests(unittest.TestCase):
    def test_consecutive_identical_logs_are_deduplicated(self):
        api = app.Api.__new__(app.Api)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir()
            line = 'level=warning msg="dial tcp [2001:db8::1]:80 unreachable"'
            (logs / "core.log").write_text("\n".join([line, line, "different"]), encoding="utf-8")
            with mock.patch.object(app, "data_dir", return_value=root):
                result = api.get_logs()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["lines"]), 2)


if __name__ == "__main__":
    unittest.main()
