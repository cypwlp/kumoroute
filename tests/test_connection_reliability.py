import importlib.util
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_reliability", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class FakeStore:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.saved = 0

    def save(self):
        self.saved += 1


class FakeCore:
    def __init__(self, up=True, reload_result=(True, "")):
        self.up = up
        self.reload_result = reload_result
        self.reloads = 0

    def is_up(self):
        return self.up

    def start(self):
        self.up = True
        return True, ""

    def reload_runtime(self):
        self.reloads += 1
        return self.reload_result


class NetworkReliabilityTests(unittest.TestCase):
    def test_first_ip_handles_quoted_ipv4_and_ipv6(self):
        self.assertEqual(app._first_ip('"203.0.113.8"'), "203.0.113.8")
        self.assertEqual(app._first_ip("2001:db8::1"), "2001:db8::1")
        self.assertEqual(app._first_ip("not-an-ip"), "")

    def test_diagnostics_confirms_dns_leak_with_real_egress_comparison(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"mixed_port": 7890, "network_mode": "coexist"})
        api._profiles = mock.Mock(entries=[])
        addr = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.51.100.5", 443))
        with mock.patch.object(app, "_has_global_ipv6", return_value=False), \
             mock.patch.object(app, "_test_ipv6_connectivity", return_value=True), \
             mock.patch.object(app, "_system_dns_servers", return_value=["192.0.2.53"]), \
             mock.patch.object(app, "_doh_template_count", return_value=0), \
             mock.patch.object(app, "_configured_dns_protocols", return_value=(0, 0)), \
             mock.patch.object(app.socket, "getaddrinfo", return_value=[addr]), \
             mock.patch.object(app, "is_system_proxy_on", return_value=True), \
             mock.patch.object(app, "_dns_query_txt", return_value='"203.0.113.9"'), \
             mock.patch.object(app, "_fetch_egress_ip", return_value="198.51.100.9"), \
             mock.patch.object(api, "get_logs", return_value={"lines": []}):
            result = api.network_diagnostics()
        self.assertTrue(result["dns_leak_confirmed"])
        self.assertEqual(result["dns_resolver_ip"], "203.0.113.9")
        self.assertEqual(result["proxy_egress_ip"], "198.51.100.9")
        self.assertTrue(any(item["type"] == "dns-leak" for item in result["issues"]))


class ProxyAndVpnRollbackTests(unittest.TestCase):
    def test_system_proxy_validation_failure_restores_original_proxy(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"mixed_port": 7890, "original_proxy": None})
        api._core = FakeCore()
        registry = {"enable": 0, "server": "", "override": ""}

        def current_proxy():
            return dict(registry)

        def apply_proxy(enable, server, override):
            registry.update({"enable": int(enable), "server": server, "override": override})

        def proxy_on(_store):
            return registry["enable"] == 1 and "127.0.0.1:" in registry["server"]

        with mock.patch.object(app, "get_system_proxy", side_effect=current_proxy), \
             mock.patch.object(app, "_apply_registry_proxy", side_effect=apply_proxy), \
             mock.patch.object(app, "is_system_proxy_on", side_effect=proxy_on), \
             mock.patch.object(app, "_probe_http", return_value={"ok": False, "error": "timeout"}), \
             mock.patch.object(app.time, "sleep"):
            result = api.set_system_proxy(True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertFalse(result["sys_proxy"])
        self.assertEqual(registry, {"enable": 0, "server": "", "override": ""})
        self.assertIsNone(api._store.data["original_proxy"])

    def test_vpn_validation_failure_disconnects_and_restores_proxy(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"vpn_restore_system_proxy": True, "vpn_proxy_pending": True})
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value={"name": "office", "saved_username": "user"}), \
             mock.patch.object(app, "_vpn_credential_read", return_value={"username": "user", "password": "secret"}), \
             mock.patch.object(api, "_vpn_prepare_proxy", return_value={"ok": True, "proxy_disabled": True}), \
             mock.patch.object(app, "_probe_http", side_effect=[
                 {"ok": True, "status": 204, "latency_ms": 20, "error": ""},
                 {"ok": False, "status": 0, "latency_ms": 8000, "error": "timeout"},
             ]), \
             mock.patch.object(app, "_vpn_ras_dial", return_value=(0, "")), \
             mock.patch.object(app, "_vpn_ras_disconnect", return_value=(True, "")) as disconnect, \
             mock.patch.object(api, "_vpn_restore_proxy", return_value=True) as restore, \
             mock.patch.object(app.time, "sleep"):
            result = api.vpn_connect("office")
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertTrue(result["disconnected"])
        self.assertTrue(result["proxy_restored"])
        disconnect.assert_called_once_with("office")
        restore.assert_called_once_with()

    def test_credential_save_failure_still_runs_network_validation(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"vpn_restore_system_proxy": True})
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value={"name": "office"}), \
             mock.patch.object(api, "_vpn_prepare_proxy", return_value=None), \
             mock.patch.object(app, "_probe_http", return_value={"ok": True, "status": 204, "latency_ms": 18, "error": ""}), \
             mock.patch.object(app, "_vpn_ras_dial", return_value=(0, "")), \
             mock.patch.object(app, "_vpn_credential_write", return_value=False), \
             mock.patch.object(app.time, "sleep"):
            result = api.vpn_connect_with_credentials("office", "user", "secret", True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["validated"])
        self.assertFalse(result["credentials_saved"])
        self.assertIn("無法保存 VPN 憑證", result["warning"])


class SubscriptionAndBackupTests(unittest.TestCase):
    def test_subscription_auto_update_is_due_and_persists_timestamp(self):
        class Profiles:
            entries = [{"id": "r1", "name": "Remote", "kind": "remote"}]
            def __init__(self):
                self.updated = []
            def update(self, pid):
                self.updated.append(pid)
                return {}
            def rollback_to(self, pid, previous):
                raise AssertionError("rollback should not run")

        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"subscription_update_hours": 6, "last_subscription_update": ""})
        api._profiles = Profiles()
        api._core = FakeCore(reload_result=(True, ""))
        result = api.subscription_auto_update(False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(api._profiles.updated, ["r1"])
        self.assertTrue(api._store.data["last_subscription_update"])

    def test_subscription_auto_update_retries_when_every_remote_fails(self):
        class Profiles:
            entries = [{"id": "r1", "name": "Remote", "kind": "remote"}]
            def update(self, pid):
                raise ValueError("offline")

        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"subscription_update_hours": 6, "last_subscription_update": ""})
        api._profiles = Profiles()
        api._core = FakeCore()
        result = api.subscription_auto_update(True)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(api._store.data["last_subscription_update"], "")
        self.assertEqual(api._core.reloads, 0)

    def test_subscription_auto_update_rolls_back_when_core_reload_fails(self):
        class Profiles:
            entries = [{"id": "r1", "name": "Remote", "kind": "remote", "updated_at": "old"}]
            def __init__(self):
                self.updated = []
                self.rolled_back = []
            def update(self, pid):
                self.updated.append(pid)
                return {}
            def rollback_to(self, pid, previous):
                self.rolled_back.append((pid, previous))

        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"subscription_update_hours": 6})
        api._profiles = Profiles()
        api._core = FakeCore(reload_result=(False, "bad config"))
        result = api.subscription_auto_update(True)
        self.assertTrue(result["reload_failed"])
        self.assertEqual(result["rolled_back"], ["Remote"])
        self.assertEqual(api._profiles.rolled_back[0][0], "r1")
        self.assertTrue(any(item["name"] == "核心重新載入" for item in result["failed"]))

    def _api(self, root):
        store = app.Store(root / "settings.json", app.DEFAULT_SETTINGS)
        profiles = app.Profiles(store, root / "profiles")
        content = "proxies: []\nrules:\n  - MATCH,DIRECT\n"
        profiles.entries.append({"id": "sub1", "name": "Sub", "kind": "local", "url": "", "updated_at": "2026-01-01T00:00:00"})
        profiles._save()
        profiles.path_of("sub1").write_text(content, encoding="utf-8")
        store.data["active_profile"] = "sub1"
        store.save()
        api = app.Api(store, profiles, FakeCore())
        api._win = mock.Mock()
        return api

    def test_backup_export_and_restore_include_settings_and_profiles_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = self._api(root)
            with mock.patch.object(app.Path, "home", return_value=root), \
                 mock.patch.object(app, "data_dir", return_value=root / "appdata"):
                exported = api.export_backup()
                self.assertTrue(exported["ok"], exported)
                backup_path = Path(exported["path"])
                payload = json.loads(backup_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema"], 1)
                self.assertNotIn("password", json.dumps(payload).lower())
                self.assertEqual(payload["profiles"][0]["name"], "Sub")

                api._store.data["mode"] = "global"
                api._store.save()
                backup_path.write_text(json.dumps({
                    "schema": 1,
                    "settings": {"mixed_port": 7897, "controller_port": 9097, "mode": "direct"},
                    "active_profile": "restored",
                    "profiles": [{
                        "id": "restored", "name": "Restored", "kind": "local", "url": "",
                        "updated_at": "2026-02-01T00:00:00",
                        "content": "proxies: []\nrules:\n  - MATCH,DIRECT\n",
                    }],
                }, ensure_ascii=False), encoding="utf-8")
                api._win.create_file_dialog.return_value = [str(backup_path)]
                restored = api.import_backup()
            self.assertTrue(restored["ok"], restored)
            self.assertEqual(api._store.data["mixed_port"], 7897)
            self.assertEqual(api._store.data["controller_port"], 9097)
            self.assertEqual(api._store.data["mode"], "direct")
            self.assertEqual(api._store.data["active_profile"], "restored")
            self.assertTrue(api._profiles.path_of("restored").is_file())
            self.assertTrue(Path(restored["safety_backup"]).is_file())

    def test_backup_refuses_to_silently_skip_a_missing_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = self._api(root)
            api._profiles.entries.append({"id": "missing", "name": "Missing", "kind": "local", "url": "", "updated_at": ""})
            with self.assertRaises(FileNotFoundError):
                api._backup_payload()

    def test_backup_restore_rejects_invalid_ports_before_mutation(self):
        api = app.Api.__new__(app.Api)
        api._store = FakeStore({"mixed_port": 7890, "controller_port": 9090})
        api._profiles = mock.Mock(entries=[])
        with self.assertRaisesRegex(ValueError, "連接埠"):
            api._apply_backup_payload({"schema": 1, "settings": {"mixed_port": 80}, "profiles": []})
        self.assertEqual(api._store.data["mixed_port"], 7890)


if __name__ == "__main__":
    unittest.main()
