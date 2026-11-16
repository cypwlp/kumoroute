import importlib.util
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_network_quality", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class FakeStore:
    def __init__(self, **data):
        self.data = dict(data)
        self.saves = 0

    def save(self):
        self.saves += 1


class FakeProfiles:
    def __init__(self, text):
        self.text = text

    def active_entry(self):
        return {"id": "active"}

    def path_of(self, _pid):
        return self.path


class NetworkModeTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore(
            network_mode="coexist",
            vpn_disable_system_proxy=True,
            vpn_restore_system_proxy=True,
        )
        self.api = app.Api.__new__(app.Api)
        self.api._store = self.store

    def test_invalid_mode_is_rejected(self):
        result = self.api.set_network_mode("invalid")
        self.assertFalse(result["ok"])
        self.assertEqual(self.store.data["network_mode"], "coexist")

    def test_vpn_mode_disables_system_proxy(self):
        with mock.patch.object(app, "is_system_proxy_on", return_value=True), \
             mock.patch.object(self.api, "set_system_proxy", return_value={"ok": True}) as disable:
            result = self.api.set_network_mode("vpn")
        self.assertTrue(result["ok"])
        disable.assert_called_once_with(False)
        self.assertEqual(self.store.data["network_mode"], "vpn")
        self.assertGreater(self.store.saves, 0)

    def test_proxy_mode_disconnects_vpn_and_enables_proxy(self):
        with mock.patch.object(self.api, "vpn_list", return_value={"ok": True, "connections": [
            {"name": "office", "connected": True},
            {"name": "home", "connected": False},
        ]}), \
             mock.patch.object(self.api, "vpn_disconnect", return_value={"ok": True}) as disconnect, \
             mock.patch.object(app, "is_system_proxy_on", return_value=False), \
             mock.patch.object(self.api, "set_system_proxy", return_value={"ok": True}) as enable:
            result = self.api.set_network_mode("proxy")
        self.assertTrue(result["ok"])
        disconnect.assert_called_once_with("office")
        enable.assert_called_once_with(True)
        self.assertEqual(self.store.data["network_mode"], "proxy")

    def test_proxy_mode_reports_vpn_disconnect_failure(self):
        with mock.patch.object(self.api, "vpn_list", return_value={"ok": True, "connections": [
            {"name": "office", "connected": True},
        ]}), \
             mock.patch.object(self.api, "vpn_disconnect", return_value={"ok": False, "error": "denied"}), \
             mock.patch.object(app, "is_system_proxy_on", return_value=False):
            result = self.api.set_network_mode("proxy")
        self.assertFalse(result["ok"])
        self.assertIn("denied", result["error"])
        self.assertEqual(self.store.data["network_mode"], "coexist")


class VpnProxyCoordinationTests(unittest.TestCase):
    def _api(self, **data):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore(**data)
        return api

    def test_disconnect_restores_proxy(self):
        api = self._api(vpn_proxy_pending=True, vpn_restore_system_proxy=True)
        profile = {"name": "office"}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value=profile), \
             mock.patch.object(app.subprocess, "run", return_value=completed), \
             mock.patch.object(api, "set_system_proxy", return_value={"ok": True}) as restore:
            result = api.vpn_disconnect("office")
        self.assertTrue(result["ok"])
        self.assertTrue(result["proxy_restored"])
        restore.assert_called_once_with(True)
        self.assertFalse(api._store.data["vpn_proxy_pending"])

    def test_connection_failure_restores_prepared_proxy(self):
        api = self._api(vpn_disable_system_proxy=True, vpn_restore_system_proxy=True)
        profile = {"name": "office", "saved_username": "user"}
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value=profile), \
             mock.patch.object(app, "_vpn_credential_read", return_value={"username": "u", "password": "p"}), \
             mock.patch.object(app, "is_system_proxy_on", return_value=True), \
             mock.patch.object(api, "set_system_proxy", side_effect=[{"ok": True}, {"ok": True}]) as proxy, \
             mock.patch.object(app, "_vpn_ras_dial", return_value=(809, "timeout")):
            result = api.vpn_connect("office")
        self.assertFalse(result["ok"])
        self.assertEqual([call.args[0] for call in proxy.call_args_list], [False, True])
        self.assertFalse(api._store.data["vpn_proxy_pending"])

    def test_restore_setting_controls_proxy_restore(self):
        api = self._api(vpn_proxy_pending=True, vpn_restore_system_proxy=False)
        with mock.patch.object(app, "is_system_proxy_on", return_value=True), \
             mock.patch.object(api, "set_system_proxy") as proxy:
            restored = api._vpn_restore_proxy()
        self.assertFalse(restored)
        proxy.assert_not_called()
        self.assertFalse(api._store.data["vpn_proxy_pending"])

    def test_restore_toggle_persists(self):
        api = self._api(vpn_restore_system_proxy=True)
        result = api.vpn_set_restore_proxy(False)
        self.assertTrue(result["ok"])
        self.assertFalse(api._store.data["vpn_restore_system_proxy"])
        self.assertGreater(api._store.saves, 0)


class NetworkDiagnosticsTests(unittest.TestCase):
    def _profiles_with_dns(self, text):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "profile.yaml"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(temp.cleanup)
        profiles = FakeProfiles.__new__(FakeProfiles)
        profiles.path = path
        return profiles

    def test_diagnostics_expose_encrypted_dns_and_group_events(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore(network_mode="coexist", vpn_proxy_pending=False)
        api._profiles = self._profiles_with_dns(
            "mode: rule\ndns:\n  nameserver:\n    - https://dns.example/dns-query\n    - tls://dot.example\n"
        )
        logs = ["IPv6 unreachable network"] * 3 + ["DNS lookup failed"] * 2
        addresses = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0))]
        with mock.patch.object(app, "_has_global_ipv6", return_value=True), \
             mock.patch.object(app, "_test_ipv6_connectivity", return_value=False), \
             mock.patch.object(app, "_system_dns_servers", return_value=["8.8.8.8"]), \
             mock.patch.object(app, "_doh_template_count", return_value=1), \
             mock.patch.object(app, "is_system_proxy_on", return_value=True), \
             mock.patch.object(app.socket, "getaddrinfo", return_value=addresses), \
             mock.patch.object(api, "get_logs", return_value={"lines": logs}):
            result = api.network_diagnostics()
        self.assertTrue(result["ok"])
        self.assertEqual(result["system_doh_templates"], 1)
        self.assertEqual(result["config_doh_templates"], 1)
        self.assertEqual(result["dot_templates"], 1)
        self.assertTrue(result["dns_encryption_conflict"])
        self.assertTrue(result["ipv6_preferred"])
        issue_types = {item["type"]: item for item in result["issues"]}
        self.assertEqual(issue_types["ipv6"]["count"], 4)
        self.assertEqual(issue_types["dns"]["count"], 2)
        self.assertIn("dns-leak", issue_types)
        self.assertIn("ipv6-preference", issue_types)
        self.assertIn("dns-encrypted", issue_types)

    def test_repair_actions_persist_and_reload(self):
        actions = [
            ("ipv6", "force_disable_ipv6", True),
            ("dns", "dns_mode", "backup"),
            ("dns-system", "dns_mode", "auto"),
        ]
        for action, key, expected in actions:
            with self.subTest(action=action):
                api = app.Api.__new__(app.Api)
                api._store = FakeStore(force_disable_ipv6=False, dns_mode="auto")
                api._core = mock.Mock()
                api._core.reload_runtime.return_value = (True, "")
                result = api.network_repair(action)
                self.assertTrue(result["ok"])
                self.assertEqual(api._store.data[key], expected)
                self.assertGreater(api._store.saves, 0)
                api._core.reload_runtime.assert_called_once()

    def test_repair_rolls_back_when_core_reload_fails(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore(force_disable_ipv6=False, dns_mode="auto")
        api._core = mock.Mock()
        api._core.reload_runtime.return_value = (False, "reload failed")
        result = api.network_repair("ipv6")
        self.assertFalse(result["ok"])
        self.assertIn("reload failed", result["error"])
        self.assertFalse(api._store.data["force_disable_ipv6"])

    def test_dns_flush_does_not_reload_core(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore(dns_mode="auto")
        api._core = mock.Mock()
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(app.subprocess, "run", return_value=completed) as run:
            result = api.network_repair("flush")
        self.assertTrue(result["ok"])
        run.assert_called_once()
        api._core.reload_runtime.assert_not_called()


class UiAndContractTests(unittest.TestCase):
    def test_quality_and_strategy_controls_are_wired(self):
        js = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        for marker in [
            "consecutiveTimeouts(group.name, node.name) >= 2",
            "Math.min(6, nodes.length)",
            "cancelGroupTest",
            "button.disabled = false",
            "history.push({ t: now, ms, reason:",
            "localStorage.setItem(PROXY_STRATEGY_KEY + \".modes\"",
            "data-proxy-strategy",
            "data-retest-node",
            "last.ms !== null",
        ]:
            self.assertIn(marker, js)
        self.assertLess(js.index("const PROXY_STRATEGY_KEY"), js.index("let proxyStrategies = loadProxyStrategies()"))
        for marker in ["data-network-mode=\"proxy\"", "id=\"toggle-vpn-restore-proxy\"", "id=\"network-diagnostics-result\""]:
            self.assertIn(marker, html)
        self.assertIn("await applyProxyStrategy();", js)


if __name__ == "__main__":
    unittest.main()
