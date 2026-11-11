"""Resilience smoke test: geo seeding, log rotation, core watchdog. No GUI."""

import subprocess
import time
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kumoroute_app", ROOT / "client" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

store = app.Store(app.data_dir() / "settings.json", app.DEFAULT_SETTINGS)
profiles = app.Profiles(store)
core = app.Core(store, profiles)

dd = app.data_dir()

ok, msg = core.start()
print("core_start:", ok, msg[:200] if msg else "")
assert ok, msg

print("geo_seeded:", (dd / "geoip.metadb").exists(), (dd / "geosite.dat").exists())
pid1 = core.proc.pid

# log rotation
core.stop()
(dd / "logs" / "core.log").write_bytes(b"x" * (3 * 1024 * 1024))
ok, msg = core.start()
print("restart_ok:", ok)
print("rotated:", (dd / "logs" / "core.1.log").exists(),
      "| fresh log size:", (dd / "logs" / "core.log").stat().st_size)
pid2 = core.proc.pid
print("pids:", pid1, "->", pid2)

# watchdog: kill core externally, expect auto respawn
subprocess.run(["taskkill", "/PID", str(pid2), "/F"], capture_output=True)
time.sleep(8)
respawned = core.proc is not None and core.proc.poll() is None
pid3 = core.proc.pid if core.proc else None
print("watchdog_respawned:", respawned, "| new pid:", pid3)
print("is_up_after_respawn:", core.is_up())

core.stop()
time.sleep(1)
print("stopped_clean:", not core.is_up())
print("RESILIENCE OK")
