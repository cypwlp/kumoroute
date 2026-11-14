import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app_vpn", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class WindowsVpnTests(unittest.TestCase):
    def test_non_windows_is_reported_as_unsupported(self):
        with mock.patch.object(app.platform, "system", return_value="Linux"):
            result = app.Api.__new__(app.Api).vpn_list()
        self.assertTrue(result["ok"])
        self.assertFalse(result["supported"])
        self.assertEqual(result["connections"], [])
        self.assertEqual(result["advanced"], {"allow_metered": True, "allow_roaming": True})

    def test_windows_vpn_list_is_normalized(self):
        payload = json.dumps({
            "Connections": [{
                "Name": "vn",
                "ServerAddress": "192.168.86.18",
                "TunnelType": "Pptp",
                "ConnectionStatus": "Connected",
                "RememberCredential": True,
                "AllUserConnection": False,
            }],
            "AllowMetered": False,
            "AllowRoaming": True,
        })
        completed = mock.Mock(returncode=0, stdout=payload, stderr="")
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(app.subprocess, "run", return_value=completed), \
             mock.patch.object(app, "_vpn_credential_read", return_value={"username": "super", "password": "secret"}):
            result = app.Api.__new__(app.Api).vpn_list()
        self.assertTrue(result["ok"])
        self.assertTrue(result["supported"])
        self.assertEqual(result["connections"][0]["name"], "vn")
        self.assertTrue(result["connections"][0]["connected"])
        self.assertTrue(result["connections"][0]["credential_saved"])
        self.assertEqual(result["connections"][0]["saved_username"], "super")
        self.assertEqual(result["advanced"], {"allow_metered": False, "allow_roaming": True})

    def test_legacy_list_payload_is_still_accepted(self):
        payload = json.dumps([{
            "Name": "home",
            "ServerAddress": "vpn.example.com",
            "TunnelType": "Ikev2",
            "ConnectionStatus": "Disconnected",
            "RememberCredential": False,
            "AllUserConnection": True,
        }])
        completed = mock.Mock(returncode=0, stdout=payload, stderr="")
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(app.subprocess, "run", return_value=completed), \
             mock.patch.object(app, "_vpn_credential_read", return_value=None):
            result = app.Api.__new__(app.Api).list_vpn_connections()
        self.assertTrue(result["ok"])
        self.assertEqual(result["connections"][0]["type"], "Ikev2")
        self.assertTrue(result["connections"][0]["all_user"])
        self.assertEqual(result["advanced"], {"allow_metered": True, "allow_roaming": True})

    def test_connect_without_saved_credential_requests_login(self):
        api = app.Api.__new__(app.Api)
        profile = {"name": "vn", "saved_username": ""}
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value=profile), \
             mock.patch.object(app, "_vpn_credential_read", return_value=None):
            result = api.vpn_connect("vn")
        self.assertFalse(result["ok"])
        self.assertTrue(result["needs_credentials"])

    def test_connect_uses_saved_credential_and_native_rasdial(self):
        api = app.Api.__new__(app.Api)
        profile = {"name": "vn", "saved_username": "super"}
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value=profile), \
             mock.patch.object(app, "_vpn_credential_read", return_value={"username": "super", "password": "secret"}), \
             mock.patch.object(app, "_vpn_ras_dial", return_value=(0, "")) as dial:
            result = api.vpn_connect("vn")
        self.assertTrue(result["ok"])
        dial.assert_called_once_with("vn", "super", "secret")

    def test_stale_saved_credential_is_deleted_and_requests_login(self):
        api = app.Api.__new__(app.Api)
        profile = {"name": "vn", "saved_username": "super"}
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value=profile), \
             mock.patch.object(app, "_vpn_credential_read", return_value={"username": "super", "password": "old"}), \
             mock.patch.object(app, "_vpn_ras_dial", return_value=(691, "bad password")), \
             mock.patch.object(app, "_vpn_credential_delete") as delete:
            result = api.vpn_connect("vn")
        self.assertTrue(result["needs_credentials"])
        self.assertTrue(result["stale_credentials"])
        delete.assert_called_once_with("vn")

    def test_connect_with_credentials_saves_in_windows_credential_manager(self):
        api = app.Api.__new__(app.Api)
        profile = {"name": "vn"}
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value=profile), \
             mock.patch.object(app, "_vpn_ras_dial", return_value=(0, "")) as dial, \
             mock.patch.object(app, "_vpn_credential_write", return_value=True) as save:
            result = api.vpn_connect_with_credentials("vn", " super ", "secret", True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["credentials_saved"])
        dial.assert_called_once_with("vn", "super", "secret")
        save.assert_called_once_with("vn", "super", "secret")

    def test_advanced_setting_rejects_unknown_name(self):
        with mock.patch.object(app.platform, "system", return_value="Windows"):
            result = app.Api.__new__(app.Api).vpn_set_advanced("unknown", True)
        self.assertFalse(result["ok"])

    def test_advanced_setting_writes_expected_registry_dword(self):
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(app.subprocess, "run", return_value=completed) as run:
            result = app.Api.__new__(app.Api).vpn_set_advanced("metered", True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["pending"])
        args = run.call_args.args[0]
        self.assertIn("NoCostedNetwork", args)
        self.assertIn("/d", args)
        self.assertEqual(args[args.index("/d") + 1], "0")

    def test_advanced_setting_uses_uac_when_not_elevated(self):
        completed = mock.Mock(returncode=1, stdout="", stderr="access denied")
        process = mock.Mock()
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(app.subprocess, "run", return_value=completed), \
             mock.patch.object(app.subprocess, "Popen", return_value=process) as popen:
            result = app.Api.__new__(app.Api).vpn_set_advanced("roaming", False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["pending"])
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "powershell.exe")
        script = command[-1]
        self.assertIn("NoRoamingNetwork", script)
        self.assertIn("'/d','1'", script)

    def test_vpn_forget_credentials_deletes_stored_secret(self):
        api = app.Api.__new__(app.Api)
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(app, "_vpn_credential_delete") as delete:
            result = api.vpn_forget_credentials("vn")
        self.assertTrue(result["ok"])
        delete.assert_called_once_with("vn")

    def test_vpn_auto_proxy_setting_persists(self):
        class FakeStore:
            data = {"vpn_disable_system_proxy": True}
            def save(self):
                self.saved = True
        api = app.Api.__new__(app.Api)
        api._store = FakeStore()
        result = api.vpn_set_auto_proxy(False)
        self.assertTrue(result["ok"])
        self.assertFalse(api._store.data["vpn_disable_system_proxy"])
        self.assertTrue(api._store.saved)

    def test_vpn_add_and_delete_use_profile_commands(self):
        api = app.Api.__new__(app.Api)
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(app, "_vpn_profile_command", return_value=(True, "")) as run:
            added = api.vpn_add("office", "vpn.example.com", "pptp")
        self.assertTrue(added["ok"])
        script = run.call_args.args[0]
        self.assertIn("Add-VpnConnection", script)
        self.assertIn("office", script)
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(app, "_vpn_profile_command", return_value=(True, "")), \
             mock.patch.object(app, "_vpn_credential_delete") as delete:
            removed = api.vpn_delete("office")
        self.assertTrue(removed["ok"])
        delete.assert_called_once_with("office")

    def test_vpn_connect_disables_system_proxy_when_enabled(self):
        api = app.Api.__new__(app.Api)
        api._store = type("Store", (), {"data": {"vpn_disable_system_proxy": True}})()
        profile = {"name": "vn", "saved_username": "super"}
        with mock.patch.object(app.platform, "system", return_value="Windows"), \
             mock.patch.object(api, "_vpn_profile", return_value=profile), \
             mock.patch.object(app, "_vpn_credential_read", return_value={"username": "super", "password": "secret"}), \
             mock.patch.object(app, "is_system_proxy_on", return_value=True), \
             mock.patch.object(api, "set_system_proxy", return_value={"ok": True}) as disable, \
             mock.patch.object(app, "_vpn_ras_dial", return_value=(0, "")):
            result = api.vpn_connect("vn")
        self.assertTrue(result["ok"])
        disable.assert_called_once_with(False)

    def test_vpn_ui_and_tauri_are_wired(self):
        html = (ROOT / "client" / "ui" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "client" / "ui" / "app.js").read_text(encoding="utf-8")
        capabilities = (ROOT / "tauri" / "capabilities" / "main.json").read_text(encoding="utf-8")
        self.assertIn('data-page="vpn"', html)
        self.assertIn('id="page-vpn"', html)
        self.assertIn('id="btn-vpn-refresh"', html)
        self.assertIn('id="btn-vpn-settings"', html)
        self.assertIn('id="toggle-vpn-metered"', html)
        self.assertIn('id="toggle-vpn-roaming"', html)
        self.assertIn('id="vpn-credential-modal"', html)
        self.assertIn('id="vpn-credential-form"', html)
        self.assertIn('id="vpn-profile-modal"', html)
        self.assertIn('id="toggle-vpn-auto-proxy"', html)
        self.assertIn('api("vpn_list")', js)
        self.assertIn('openVpnProfileModal("add")', js)
        self.assertIn('api("vpn_add", name, server, type)', js)
        self.assertIn('vpn_forget_credentials: ["name"]', js)
        self.assertIn('data-vpn-action="forget_credentials"', js)
        self.assertIn('api("vpn_set_advanced", setting, enabled)', js)
        self.assertIn('api("vpn_connect_with_credentials", name, username, password, remember)', js)
        self.assertIn('vpn_connect_with_credentials: ["name", "username", "password", "remember"]', js)
        self.assertIn('vpn_set_advanced: ["setting", "enabled"]', js)
        self.assertIn('allow-vpn-set-advanced', capabilities)
        self.assertIn('allow-vpn-connect-with-credentials', capabilities)
        self.assertIn('allow-vpn-add', capabilities)
        self.assertIn('allow-vpn-edit', capabilities)
        self.assertIn('allow-vpn-delete', capabilities)
        self.assertIn('allow-test-node-delay', capabilities)


if __name__ == "__main__":
    unittest.main()
