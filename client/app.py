"""KumoRoute - lightweight Clash/mihomo desktop client."""

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import webview
import yaml

APP_NAME = "KumoRoute"
LEGACY_APP_NAME = "MyClash"
APP_VERSION = "0.3.0"
CREATE_NO_WINDOW = 0x08000000
SUB_UA = f"KumoRoute/{APP_VERSION}"
TEST_URL = "https://cp.cloudflare.com/generate_204"
INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
PROXY_OVERRIDE = (
    "<local>;localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;"
    "172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;"
    "172.29.*;172.30.*;172.31.*;192.168.*"
)
BUILTIN_CONFIG = """mode: rule
log-level: info
proxies: []
rules:
  - MATCH,DIRECT
"""

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _frozen():
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    if _frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def exe_dir() -> Path:
    if _frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    d = base / APP_NAME
    legacy = base / LEGACY_APP_NAME
    if not d.exists() and legacy.is_dir():
        try:
            legacy.rename(d)
        except OSError:
            pass
    (d / "profiles").mkdir(parents=True, exist_ok=True)
    (d / "logs").mkdir(parents=True, exist_ok=True)
    return d


def core_binary() -> Path | None:
    for p in (exe_dir() / "core" / "mihomo.exe", resource_dir() / "core" / "mihomo.exe"):
        if p.is_file():
            return p
    return None


MAX_LOG_BYTES = 2 * 1024 * 1024
GEO_FILES = ("geoip.metadb", "geosite.dat")


def ensure_geo_files() -> None:
    binp = core_binary()
    if not binp:
        return
    src = binp.parent
    dd = data_dir()
    for name in GEO_FILES:
        dst = dd / name
        if not dst.exists():
            f = src / name
            if f.exists():
                try:
                    shutil.copyfile(f, dst)
                except OSError:
                    pass


def rotate_core_log() -> None:
    p = data_dir() / "logs" / "core.log"
    try:
        if p.exists() and p.stat().st_size > MAX_LOG_BYTES:
            bak = data_dir() / "logs" / "core.1.log"
            bak.unlink(missing_ok=True)
            p.replace(bak)
    except OSError:
        pass


def app_log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n"
    try:
        with open(data_dir() / "logs" / "app.log", "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def message_box(text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, text, APP_NAME, 0x40)
    except Exception:
        pass


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


DEFAULT_SETTINGS = {
    "mixed_port": 7890,
    "controller_port": 9090,
    "mode": "rule",
    "active_profile": "",
    "original_proxy": None,
}


class Store:
    def __init__(self, path: Path, default: dict):
        self.path = path
        self.lock = threading.Lock()
        self.data = dict(default)
        try:
            if path.is_file():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
        except Exception as exc:
            app_log(f"settings load failed: {exc}")

    def save(self) -> None:
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)


def get_system_proxy() -> dict:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as k:
            try:
                enable = int(winreg.QueryValueEx(k, "ProxyEnable")[0])
            except FileNotFoundError:
                enable = 0
            try:
                server = str(winreg.QueryValueEx(k, "ProxyServer")[0])
            except FileNotFoundError:
                server = ""
            try:
                override = str(winreg.QueryValueEx(k, "ProxyOverride")[0])
            except FileNotFoundError:
                override = ""
        return {"enable": enable, "server": server, "override": override}
    except OSError:
        return {"enable": 0, "server": "", "override": ""}


def _apply_registry_proxy(enable: int, server: str, override: str) -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE
    ) as k:
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
        winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
        winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, override)
    ctypes.windll.wininet.InternetSetOptionW(0, 39, 0, 0)
    ctypes.windll.wininet.InternetSetOptionW(0, 37, 0, 0)


def is_system_proxy_on(store: Store) -> bool:
    cur = get_system_proxy()
    return cur["enable"] == 1 and "127.0.0.1:" in cur["server"]


class Profiles:
    def __init__(self, store: Store):
        self._store = store
        self.root = data_dir() / "profiles"
        self.index_path = self.root / "index.json"
        self.lock = threading.Lock()
        self.entries: list[dict] = []
        try:
            if self.index_path.is_file():
                self.entries = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception as exc:
            app_log(f"profiles index load failed: {exc}")
        self._ensure_default()

    def _save(self) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    def _ensure_default(self) -> None:
        if not self.entries:
            f = self.root / "direct.yaml"
            if not f.exists():
                f.write_text(BUILTIN_CONFIG, encoding="utf-8")
            self.entries.append(
                {
                    "id": "direct",
                    "name": "內建直連（DIRECT）",
                    "kind": "builtin",
                    "url": "",
                    "updated_at": _now(),
                }
            )
            self._save()
        active = self._store.data.get("active_profile")
        if not active or not self.get(active):
            self._store.data["active_profile"] = self.entries[0]["id"]
            self._store.save()

    def get(self, pid: str) -> dict | None:
        return next((e for e in self.entries if e["id"] == pid), None)

    def active_entry(self) -> dict:
        return self.get(self._store.data.get("active_profile")) or self.entries[0]

    def path_of(self, pid: str) -> Path:
        return self.root / f"{pid}.yaml"

    @staticmethod
    def _validate(text: str) -> None:
        try:
            cfg = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(f"YAML 解析失敗：{exc}") from exc
        if not isinstance(cfg, dict):
            raise ValueError(
                "訂閱內容不是 Clash YAML 配置（可能是 Base64 節點清單），"
                "請先透過訂閱轉換服務轉換成 Clash 格式再匯入。"
            )

    @staticmethod
    def _fetch(url: str) -> str:
        req = urllib.request.Request(
            url, headers={"User-Agent": SUB_UA, "Accept": "*/*"}
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("訂閱檔案超過 10MB，已中止")
        return raw.decode("utf-8", "replace")

    def add_remote(self, url: str, name: str) -> dict:
        url = (url or "").strip()
        if not re.match(r"^https?://", url, re.I):
            raise ValueError("訂閱連結必須是 http(s):// 開頭")
        text = self._fetch(url)
        self._validate(text)
        pid = uuid.uuid4().hex[:8]
        self.path_of(pid).write_text(text, encoding="utf-8")
        name = (name or "").strip() or (urllib.parse.urlparse(url).hostname or f"訂閱 {len(self.entries) + 1}")
        entry = {
            "id": pid,
            "name": name,
            "kind": "remote",
            "url": url,
            "updated_at": _now(),
        }
        with self.lock:
            self.entries.append(entry)
            self._save()
        return entry

    def add_local(self, src: str) -> dict:
        p = Path(src)
        text = p.read_text(encoding="utf-8", errors="replace")
        self._validate(text)
        pid = uuid.uuid4().hex[:8]
        self.path_of(pid).write_text(text, encoding="utf-8")
        entry = {
            "id": pid,
            "name": p.stem,
            "kind": "local",
            "url": "",
            "updated_at": _now(),
        }
        with self.lock:
            self.entries.append(entry)
            self._save()
        return entry

    def update(self, pid: str) -> dict:
        entry = self.get(pid)
        if not entry:
            raise ValueError("找不到該訂閱")
        if entry["kind"] != "remote" or not entry.get("url"):
            raise ValueError("只有遠端訂閱可以更新")
        text = self._fetch(entry["url"])
        self._validate(text)
        self.path_of(pid).write_text(text, encoding="utf-8")
        entry["updated_at"] = _now()
        with self.lock:
            self._save()
        return entry

    def delete(self, pid: str) -> None:
        entry = self.get(pid)
        if not entry:
            return
        if entry["kind"] == "builtin":
            raise ValueError("內建配置不能刪除")
        with self.lock:
            self.entries = [e for e in self.entries if e["id"] != pid]
            self._save()
        try:
            self.path_of(pid).unlink(missing_ok=True)
        except OSError:
            pass
        if self._store.data.get("active_profile") == pid:
            self._store.data["active_profile"] = self.entries[0]["id"]
            self._store.save()

    def build_runtime(self) -> Path:
        entry = self.active_entry()
        text = self.path_of(entry["id"]).read_text(encoding="utf-8", errors="replace")
        cfg = yaml.safe_load(text) or {}
        if not isinstance(cfg, dict):
            raise ValueError("配置內容無效")
        cfg["mixed-port"] = int(self._store.data["mixed_port"])
        cfg["allow-lan"] = False
        cfg["external-controller"] = f"127.0.0.1:{int(self._store.data['controller_port'])}"
        cfg["secret"] = ""
        cfg["mode"] = self._store.data.get("mode", "rule")
        cfg["log-level"] = "info"
        cfg.setdefault("unified-delay", True)
        cfg.setdefault("tcp-concurrent", True)
        prof = cfg.get("profile")
        if not isinstance(prof, dict):
            prof = {}
        prof["store-selected"] = True
        cfg["profile"] = prof
        rules = cfg.get("rules")
        if not isinstance(rules, list):
            rules = []
        if not any(isinstance(r, str) and r.strip().upper().startswith("MATCH") for r in rules):
            rules.append("MATCH,DIRECT")
        cfg["rules"] = rules
        out = data_dir() / "runtime.yaml"
        out.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return out


class Core:
    def __init__(self, store: Store, profiles: Profiles):
        self._store = store
        self._profiles = profiles
        self.proc: subprocess.Popen | None = None
        self.logf = None
        self.lock = threading.RLock()
        self._watch = False
        self._wd_running = False

    def base_url(self) -> str:
        return f"http://127.0.0.1:{int(self._store.data['controller_port'])}"

    def api(self, method: str, path: str, body=None, timeout: float = 6):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.base_url() + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        return json.loads(raw.decode("utf-8")) if raw else None

    def version(self) -> str | None:
        try:
            return self.api("GET", "/version", timeout=2).get("version")
        except Exception:
            return None

    def is_up(self) -> bool:
        return self.version() is not None

    def start(self) -> tuple[bool, str]:
        with self.lock:
            if self.is_up():
                return True, ""
            binary = core_binary()
            if not binary:
                return False, "找不到 mihomo 核心（core/mihomo.exe）"
            ensure_geo_files()
            rotate_core_log()
            runtime = self._profiles.build_runtime()
            self.logf = open(data_dir() / "logs" / "core.log", "ab", buffering=0)
            self.logf.write(f"\n===== {_now()} 啟動核心 =====\n".encode("utf-8"))
            self.proc = subprocess.Popen(
                [str(binary), "-d", str(data_dir()), "-f", str(runtime)],
                cwd=str(data_dir()),
                stdout=self.logf,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            for _ in range(48):
                time.sleep(0.25)
                if self.is_up():
                    app_log(f"core up, pid={self.proc.pid}")
                    self._watch = True
                    if not self._wd_running:
                        self._wd_running = True
                        threading.Thread(target=self._watchdog, daemon=True).start()
                    return True, ""
                if self.proc.poll() is not None:
                    break
            tail = self.log_tail(1200)
            app_log(f"core start failed: {tail}")
            self.stop()
            return False, tail or "核心未能在 12 秒內啟動"

    def stop(self) -> None:
        with self.lock:
            self._watch = False
            if self.proc is not None:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=6)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
                self.proc = None
            if self.logf is not None:
                try:
                    self.logf.close()
                except Exception:
                    pass
                self.logf = None

    def _watchdog(self) -> None:
        storms: list[float] = []
        try:
            while self._watch:
                time.sleep(2)
                if not self._watch:
                    return
                with self.lock:
                    if self.proc is None or self.proc.poll() is None:
                        continue
                    self.proc = None
                now = time.time()
                storms = [t for t in storms if now - t < 60]
                storms.append(now)
                if len(storms) > 5:
                    app_log("core 重複崩潰超過 5 次/分鐘，停止自動重啟")
                    self._watch = False
                    return
                app_log("core 異常退出，1.5 秒後自動重啟")
                time.sleep(1.5)
                if not self._watch:
                    return
                try:
                    ok, msg = self.start()
                    if ok:
                        app_log("core 已自動重啟")
                    else:
                        app_log(f"core 自動重啟失敗：{msg[:300]}")
                        self._watch = False
                except Exception as exc:
                    app_log(f"core 自動重啟異常：{exc}")
                    self._watch = False
        finally:
            self._wd_running = False

    def log_tail(self, max_bytes: int = 8000) -> str:
        p = data_dir() / "logs" / "core.log"
        try:
            with open(p, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
                text = f.read().decode("utf-8", "replace")
            lines = [ANSI_RE.sub("", ln) for ln in text.splitlines() if ln.strip()]
            return "\n".join(lines[-25:])
        except OSError:
            return ""

    def reload_runtime(self) -> tuple[bool, str]:
        if not self.is_up():
            return True, ""
        try:
            runtime = self._profiles.build_runtime()
            self.api("PUT", "/configs", {"path": str(runtime), "force": True}, timeout=10)
            return True, ""
        except Exception as exc:
            app_log(f"reload via api failed: {exc}, restarting core")
            self.stop()
            return self.start()


class Api:
    def __init__(self, store: Store, profiles: Profiles, core: Core):
        self._store = store
        self._profiles = profiles
        self._core = core
        self._win = None
        self._on_quit = None

    # ---- state ----

    def _public_entry(self, entry: dict | None) -> dict | None:
        if not entry:
            return None
        return {k: entry.get(k, "") for k in ("id", "name", "kind", "updated_at")}

    def get_state(self) -> dict:
        running = self._core.is_up()
        mode = self._store.data.get("mode", "rule")
        if running:
            try:
                mode = self._core.api("GET", "/configs").get("mode", mode)
            except Exception:
                pass
        return {
            "app_version": APP_VERSION,
            "core_version": self._core.version() if running else None,
            "running": running,
            "sys_proxy": is_system_proxy_on(self._store),
            "mode": mode,
            "mixed_port": int(self._store.data["mixed_port"]),
            "controller_port": int(self._store.data["controller_port"]),
            "active_profile": self._public_entry(self._profiles.active_entry()),
            "profiles": [self._public_entry(e) for e in self._profiles.entries],
            "data_dir": str(data_dir()),
            "core_found": core_binary() is not None,
            "test_url": TEST_URL,
        }

    def is_sys_proxy(self) -> bool:
        return is_system_proxy_on(self._store)

    # ---- core control ----

    def start_core(self) -> dict:
        ok, msg = self._core.start()
        return {"ok": ok, "error": msg}

    def stop_core(self) -> dict:
        try:
            if is_system_proxy_on(self._store):
                self.set_system_proxy(False)
            self._core.stop()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def set_mode(self, mode: str) -> dict:
        if mode not in ("rule", "global", "direct"):
            return {"ok": False, "error": "無效的模式"}
        self._store.data["mode"] = mode
        self._store.save()
        try:
            if self._core.is_up():
                self._core.api("PATCH", "/configs", {"mode": mode})
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def set_system_proxy(self, enabled: bool) -> dict:
        try:
            if enabled:
                if not self._core.is_up():
                    ok, msg = self._core.start()
                    if not ok:
                        return {"ok": False, "error": "核心啟動失敗：" + msg}
                cur = get_system_proxy()
                ours = cur["enable"] == 1 and cur["server"].startswith("127.0.0.1:")
                if not ours and not self._store.data.get("original_proxy"):
                    self._store.data["original_proxy"] = cur
                _apply_registry_proxy(
                    1,
                    f"127.0.0.1:{int(self._store.data['mixed_port'])}",
                    PROXY_OVERRIDE,
                )
                self._store.save()
                time.sleep(1.2)
                if not is_system_proxy_on(self._store):
                    self._store.data["original_proxy"] = None
                    self._store.save()
                    return {
                        "ok": False,
                        "error": "系統代理被其他軟體改回（常見於安全軟體／網路加速器的代理守護）。"
                        "請關閉該功能後再試。",
                        "sys_proxy": False,
                    }
            else:
                orig = self._store.data.get("original_proxy")
                if orig:
                    _apply_registry_proxy(
                        int(orig.get("enable", 0)),
                        str(orig.get("server", "")),
                        str(orig.get("override", "")),
                    )
                else:
                    _apply_registry_proxy(0, "", "")
                self._store.data["original_proxy"] = None
                self._store.save()
            return {"ok": True, "sys_proxy": is_system_proxy_on(self._store)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ---- proxies ----

    def get_proxy_groups(self) -> dict:
        if not self._core.is_up():
            return {"ok": True, "groups": []}
        try:
            data = self._core.api("GET", "/proxies", timeout=8)
            proxies = data.get("proxies") or {}
            groups = []
            for name, p in proxies.items():
                if p.get("type") not in (
                    "Selector",
                    "URLTest",
                    "Fallback",
                    "LoadBalance",
                    "Relay",
                ):
                    continue
                nodes = []
                for n in p.get("all") or []:
                    np = proxies.get(n) or {}
                    nodes.append({"name": n, "type": np.get("type", "")})
                groups.append(
                    {
                        "name": name,
                        "type": p.get("type"),
                        "now": p.get("now", ""),
                        "nodes": nodes,
                    }
                )
            groups.sort(key=lambda g: (g["name"] == "GLOBAL", g["name"].lower()))
            return {"ok": True, "groups": groups}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "groups": []}

    def select_proxy(self, group: str, name: str) -> dict:
        try:
            self._core.api(
                "PUT", f"/proxies/{quote(group, safe='')}", {"name": name}
            )
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def test_group_delay(self, group: str) -> dict:
        try:
            res = self._core.api(
                "GET",
                f"/group/{quote(group, safe='')}/delay"
                f"?timeout=5000&url={quote(TEST_URL, safe='')}",
                timeout=14,
            )
            return {"ok": True, "delays": res or {}}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ---- profiles ----

    def add_subscription(self, url: str, name: str) -> dict:
        try:
            entry = self._profiles.add_remote(url, name)
            self._store.data["active_profile"] = entry["id"]
            self._store.save()
            ok, msg = self._core.reload_runtime()
            if not ok:
                return {"ok": False, "error": msg}
            return {"ok": True, "entry": self._public_entry(entry)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def import_profile(self) -> dict:
        try:
            res = self._win.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Clash 配置 (*.yaml;*.yml)", "所有檔案 (*.*)"),
            )
            if not res:
                return {"ok": False, "cancelled": True}
            src = res[0] if isinstance(res, (list, tuple)) else res
            entry = self._profiles.add_local(src)
            self._store.data["active_profile"] = entry["id"]
            self._store.save()
            ok, msg = self._core.reload_runtime()
            if not ok:
                return {"ok": False, "error": msg}
            return {"ok": True, "entry": self._public_entry(entry)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def update_profile(self, pid: str) -> dict:
        try:
            self._profiles.update(pid)
            if self._store.data.get("active_profile") == pid:
                ok, msg = self._core.reload_runtime()
                if not ok:
                    return {"ok": False, "error": msg}
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def delete_profile(self, pid: str) -> dict:
        try:
            was_active = self._store.data.get("active_profile") == pid
            self._profiles.delete(pid)
            if was_active:
                ok, msg = self._core.reload_runtime()
                if not ok:
                    return {"ok": False, "error": msg}
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def set_active_profile(self, pid: str) -> dict:
        try:
            entry = self._profiles.get(pid)
            if not entry:
                return {"ok": False, "error": "找不到該配置"}
            self._store.data["active_profile"] = pid
            self._store.save()
            ok, msg = self._core.reload_runtime()
            if not ok:
                return {"ok": False, "error": msg}
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ---- live data ----

    def get_live(self) -> dict:
        if not self._core.is_up():
            return {"running": False}
        try:
            d = self._core.api("GET", "/connections", timeout=5)
            raw = d.get("connections") or []
            connections = []
            for c in raw:
                meta = c.get("metadata") or {}
                connections.append({
                    "id": str(c.get("id") or ""),
                    "upload": int(c.get("upload") or 0),
                    "download": int(c.get("download") or 0),
                    "host": str(meta.get("host") or meta.get("destinationIP") or ""),
                    "rule": str(c.get("rule") or ""),
                    "rulePayload": str(c.get("rulePayload") or ""),
                    "chains": [str(x) for x in (c.get("chains") or [])],
                })
            return {
                "running": True,
                "up_total": int(d.get("uploadTotal") or 0),
                "down_total": int(d.get("downloadTotal") or 0),
                "count": len(raw),
                "connections": connections,
            }
        except Exception:
            return {"running": False}

    def get_logs(self) -> dict:
        p = data_dir() / "logs" / "core.log"
        try:
            with open(p, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 65536))
                text = f.read().decode("utf-8", "replace")
            lines = [ANSI_RE.sub("", ln) for ln in text.splitlines()]
            return {"ok": True, "lines": lines[-300:]}
        except OSError:
            return {"ok": True, "lines": []}

    # ---- settings / misc ----

    def save_settings(self, mixed_port: int, controller_port: int) -> dict:
        try:
            mp, cp = int(mixed_port), int(controller_port)
            if not (1024 <= mp <= 65535 and 1024 <= cp <= 65535):
                return {"ok": False, "error": "連接埠必須在 1024–65535 之間"}
            if mp == cp:
                return {"ok": False, "error": "兩個連接埠不能相同"}
            changed_mixed = mp != int(self._store.data["mixed_port"])
            changed_ctl = cp != int(self._store.data["controller_port"])
            self._store.data["mixed_port"] = mp
            self._store.data["controller_port"] = cp
            self._store.save()
            was_running = self._core.is_up()
            if was_running and (changed_mixed or changed_ctl):
                self._core.stop()
                ok, msg = self._core.start()
                if not ok:
                    return {"ok": False, "error": msg}
            if changed_mixed and is_system_proxy_on(self._store):
                _apply_registry_proxy(1, f"127.0.0.1:{mp}", PROXY_OVERRIDE)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_stats_export(self, fmt: str, content: str) -> dict:
        ext = "csv" if str(fmt).lower() == "csv" else "json"
        try:
            folder = Path.home() / "Downloads"
            if not folder.is_dir():
                folder = data_dir()
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"KumoRoute-stats-{datetime.now():%Y%m%d-%H%M%S}.{ext}"
            path.write_text(content, encoding="utf-8-sig" if ext == "csv" else "utf-8")
            return {"ok": True, "path": str(path)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_data_dir(self) -> dict:
        try:
            os.startfile(str(data_dir()))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_url(self, url: str) -> dict:
        if re.match(r"^https?://", url or "", re.I):
            webbrowser.open(url)
            return {"ok": True}
        return {"ok": False, "error": "無效的網址"}

    def quit_app(self) -> dict:
        if self._on_quit:
            threading.Thread(target=self._on_quit, daemon=True).start()
        return {"ok": True}


def build_tray(api: Api, win, state: dict):
    import pystray
    from PIL import Image

    def tray_image():
        for p in (resource_dir() / "assets" / "icon.png", None):
            if p and p.is_file():
                return Image.open(p)
        return Image.new("RGB", (64, 64), (91, 140, 255))

    def show(icon=None, item=None):
        try:
            win.show()
        except Exception:
            pass

    def toggle_proxy(icon, item):
        try:
            api.set_system_proxy(not api.is_sys_proxy())
        finally:
            icon.update_menu()

    def toggle_core(icon, item):
        try:
            if api._core.is_up():
                api.stop_core()
            else:
                api.start_core()
        finally:
            icon.update_menu()

    def quit_(icon, item):
        icon.stop()
        if api._on_quit:
            api._on_quit()

    menu = pystray.Menu(
        pystray.MenuItem("顯示主視窗", show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda item: "系統代理：開" if api.is_sys_proxy() else "系統代理：關",
            toggle_proxy,
        ),
        pystray.MenuItem(
            lambda item: "停止核心" if api._core.is_up() else "啟動核心",
            toggle_core,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出 KumoRoute", quit_),
    )
    return pystray.Icon("KumoRoute", tray_image(), "KumoRoute", menu)


_MUTEX = None


def acquire_single_instance() -> bool:
    global _MUTEX
    _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "KumoRoute_SingleInstance_Mutex")
    return ctypes.windll.kernel32.GetLastError() != 183


def _ensure_std_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> None:
    _ensure_std_streams()
    if not acquire_single_instance():
        message_box("KumoRoute 已在執行中，請從系統托盤開啟。")
        return

    store = Store(data_dir() / "settings.json", DEFAULT_SETTINGS)
    profiles = Profiles(store)
    core = Core(store, profiles)
    api = Api(store, profiles, core)

    ok, msg = core.start()
    app_log(f"core start ok={ok} msg={msg}")

    ui = resource_dir() / "ui" / "index.html"
    if not ui.is_file():
        raise RuntimeError(f"找不到 UI 檔案：{ui}")
    win = webview.create_window(
        APP_NAME,
        url=str(ui),
        js_api=api,
        width=1120,
        height=720,
        min_size=(980, 620),
        background_color="#0b0e14",
    )
    api._win = win
    state = {"really_quit": False, "tray": None}

    def on_closing():
        if state["really_quit"]:
            return True
        win.hide()
        return False

    win.events.closing += on_closing

    def do_quit():
        state["really_quit"] = True
        try:
            if state["tray"] is not None:
                state["tray"].stop()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    api._on_quit = do_quit

    def tray_thread():
        try:
            icon = build_tray(api, win, state)
            state["tray"] = icon
            icon.run()
        except Exception as exc:
            app_log(f"tray failed: {exc}")

    threading.Thread(target=tray_thread, daemon=True).start()

    if os.environ.get("KUMOROUTE_SELFTEST"):
        def selftest():
            time.sleep(7)
            try:
                v = win.evaluate_js(
                    "JSON.stringify({title: document.title,"
                    " nav: document.querySelectorAll('.nav-item').length,"
                    " st: (document.getElementById('st-text')||{}).textContent,"
                    " stVer: (document.getElementById('st-version')||{}).textContent,"
                    " demoHidden: document.getElementById('demo-banner').classList.contains('hidden'),"
                    " bridge: !!(window.pywebview && window.pywebview.api)})"
                )
                app_log(f"selftest_js: {v}")
            except Exception as exc:
                app_log(f"selftest_failed: {exc}")

        threading.Thread(target=selftest, daemon=True).start()

    auto_close = os.environ.get("KUMOROUTE_AUTOCLOSE")
    if auto_close:
        def auto():
            time.sleep(float(auto_close))
            app_log("autoclose fired")
            do_quit()

        threading.Thread(target=auto, daemon=True).start()

    try:
        webview.start(
            debug=bool(os.environ.get("KUMOROUTE_DEBUG")),
            http_server=True,
            private_mode=False,
            storage_path=str(data_dir() / "webview"),
        )
    finally:
        try:
            if is_system_proxy_on(store) or store.data.get("original_proxy"):
                api.set_system_proxy(False)
        except Exception as exc:
            app_log(f"restore proxy failed: {exc}")
        core.stop()
        app_log("exit")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        tb = traceback.format_exc()
        app_log("FATAL\n" + tb)
        message_box("KumoRoute 啟動失敗：\n" + tb[-800:])
        sys.exit(1)
