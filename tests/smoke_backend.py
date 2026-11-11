"""Backend smoke test for KumoRoute. Temporarily toggles the Windows system proxy and restores it."""

import importlib.util
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

store = app.Store(app.data_dir() / "settings.json", app.DEFAULT_SETTINGS)
profiles = app.Profiles(store)
core = app.Core(store, profiles)
api = app.Api(store, profiles, core)

print("data_dir:", app.data_dir())
print("core_binary:", app.core_binary())
before = app.get_system_proxy()
print("proxy_before:", json.dumps(before))

ok, msg = core.start()
print("core_start:", ok, msg[:300] if msg else "")
assert ok, msg

try:
    print("core_version:", core.version())
    st = api.get_state()
    print("state.running:", st["running"], "| mode:", st["mode"], "| profile:", st["active_profile"]["name"])
    print("groups:", api.get_proxy_groups())

    print("set_mode(global):", api.set_mode("global"))
    time.sleep(0.4)
    print("mode_after:", core.api("GET", "/configs").get("mode"))
    print("set_mode(rule):", api.set_mode("rule"))

    print("live:", api.get_live())
    lines = api.get_logs()["lines"]
    print("log_lines:", len(lines))
    for ln in lines[-2:]:
        print("  ", ln)

    r = api.set_system_proxy(True)
    print("proxy_enable:", r)
    mid = app.get_system_proxy()
    print("proxy_after_enable:", json.dumps(mid))
    time.sleep(0.4)
    r = api.set_system_proxy(False)
    print("proxy_disable:", r)
finally:
    if app.is_system_proxy_on(store):
        api.set_system_proxy(False)
    core.stop()

after = app.get_system_proxy()
print("proxy_after:", json.dumps(after))
print("proxy_restored_exact:", after == before)
print("core_up_after_stop:", core.is_up())
print("SMOKE OK")
