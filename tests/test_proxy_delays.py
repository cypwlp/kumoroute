import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_proxy_delays", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ProxyDelayTests(unittest.TestCase):
    def test_latest_proxy_history_delay_is_used(self):
        proxy = {"history": [
            {"time": "2026-11-14T10:00:00+08:00", "delay": 210},
            {"time": "2026-11-14T10:01:00+08:00", "delay": 148},
        ]}
        self.assertEqual(app._proxy_last_delay(proxy), 148)

    def test_extra_history_fallback_uses_newest_result(self):
        proxy = {"history": [], "extra": {
            "https://example.test/1": {"history": [{"time": "2026-11-14T10:00:00+08:00", "delay": 220}]},
            "https://example.test/2": {"history": [{"time": "2026-11-14T10:02:00+08:00", "delay": 0}]},
        }}
        self.assertEqual(app._proxy_last_delay(proxy), 0)

    def test_group_nodes_include_delay_history(self):
        class FakeCore:
            def is_up(self):
                return True
            def api(self, method, path, timeout=6):
                return {"proxies": {
                    "自動選擇": {"type": "URLTest", "now": "香港家寬-IEPL", "all": ["香港家寬-IEPL"]},
                    "香港家寬-IEPL": {
                        "type": "Trojan",
                        "history": [{"time": "2026-11-14T10:02:00+08:00", "delay": 148}],
                    },
                }}
        api = app.Api.__new__(app.Api)
        api._core = FakeCore()
        result = api.get_proxy_groups()
        self.assertTrue(result["ok"])
        self.assertEqual(result["groups"][0]["nodes"][0]["delay"], 148)
        self.assertEqual(result["groups"][0]["nodes"][0]["delay_updated_at"], "2026-11-14T10:02:00+08:00")

    def test_active_node_rendering_keeps_latency_badge(self):
        js = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn('class="node-meta"', js)
        self.assertIn("${active ? '<span class=\"node-active-label\">使用中</span>' : \"\"}", js)
        self.assertIn("${delayBadge(group.name, node)}", js)
        self.assertIn("syncGroupDelaysFromGroups();", js)
        self.assertIn('data-retest-node=', js)
        self.assertIn('proxy-node-more', js)


if __name__ == "__main__":
    unittest.main()
