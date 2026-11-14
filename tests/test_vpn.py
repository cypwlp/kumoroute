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
             mock.patch.object(app.subprocess, "run", return_value=completed):
            result = app.Api.__new__(app.Api).vpn_list()
        self.assertTrue(result["ok"])
        self.assertTrue(result["supported"])
        self.assertEqual(result["connections"][0]["name"], "vn")
        self.assertTrue(result["connections"][0]["connected"])
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
             mock.patch.object(app.subprocess, "run", return_value=completed):
            result = app.Api.__new__(app.Api).list_vpn_connections()
        self.assertTrue(result["ok"])
        self.assertEqual(result["connections"][0]["type"], "Ikev2")
        self.assertTrue(result["connections"][0]["all_user"])
        self.assertEqual(result["advanced"], {"allow_metered": True, "allow_roaming": True})

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
        self.assertIn('api("vpn_list")', js)
        self.assertIn('api("vpn_open_settings")', js)
        self.assertIn('api("vpn_set_advanced", setting, enabled)', js)
        self.assertIn('vpn_set_advanced: ["setting", "enabled"]', js)
        self.assertIn('allow-vpn-set-advanced', capabilities)


if __name__ == "__main__":
    unittest.main()
