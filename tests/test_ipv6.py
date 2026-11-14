import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_ipv6", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class IpV6DetectionTests(unittest.TestCase):
    def _run(self, count):
        completed = mock.Mock(returncode=0, stdout=str(count), stderr="")
        with mock.patch.object(app.subprocess, "run", return_value=completed):
            return app._windows_has_global_ipv6()

    def test_default_ipv6_route_enables_ipv6(self):
        self.assertTrue(self._run(1))

    def test_missing_ipv6_route_disables_ipv6(self):
        self.assertFalse(self._run(0))


if __name__ == "__main__":
    unittest.main()
