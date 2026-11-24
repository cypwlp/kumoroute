"""KumoRoute - lightweight Clash/mihomo desktop client."""

import ctypes
import hashlib
import importlib.util
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import types
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
APP_VERSION = "0.8.7"
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


def _sanitize_diagnostics_report(text: str) -> tuple[str, dict]:
    summary = {"urls": 0, "endpoints": 0, "ips": 0, "secrets": 0}
    text, summary["endpoints"] = re.subn(
        r"(?m)(-->\s*)[^\s]+", r"\1<redacted-endpoint>", text
    )
    text, summary["urls"] = re.subn(
        r"(?i)https?://[^\s\"'<>]+", "<redacted-url>", text
    )
    text, ipv4_count = re.subn(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<redacted-ip>", text)
    text, ipv6_count = re.subn(
        r"(?i)\b(?:(?:[0-9a-f]{1,4}:){1,7}:[0-9a-f]{1,4}|(?:[0-9a-f]{1,4}:){1,7}[0-9a-f]{0,3}[a-f][0-9a-f]{0,3})\b", "<redacted-ip>", text
    )
    summary["ips"] = ipv4_count + ipv6_count
    text, bearer_count = re.subn(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted-secret>", text
    )
    text, secret_count = re.subn(
        r"(?i)\b(token|secret|password|passwd|authorization|api[_-]?key|access[_-]?token)\b"
        r"(\s*[:=]\s*)([^\s,;\"'<>]+)",
        r"\1\2<redacted-secret>",
        text,
    )
    summary["secrets"] = secret_count + bearer_count
    return text, summary


def _sanitize_diagnostics(text: str) -> str:
    return _sanitize_diagnostics_report(text)[0]


def write_crash(kind: str, detail: str) -> None:
    try:
        log_dir = data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "crash.log"
        if path.exists() and path.stat().st_size > 1024 * 1024:
            backup = log_dir / "crash.1.log"
            backup.unlink(missing_ok=True)
            path.replace(backup)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {_now()} {kind} =====\n")
            f.write(_sanitize_diagnostics(detail[-200000:]))
            f.write("\n")
    except Exception:
        pass


def install_crash_hooks() -> None:
    def excepthook(exc_type, exc_value, tb):
        write_crash("uncaught", "".join(traceback.format_exception(exc_type, exc_value, tb)))
        sys.__excepthook__(exc_type, exc_value, tb)

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        detail = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        write_crash(f"thread:{args.thread.name if args.thread else ''}", detail)

    sys.excepthook = excepthook
    threading.excepthook = thread_hook


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


def is_portable_build() -> bool:
    try:
        exe = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
        return (exe.parent / "KumoRoute.portable").is_file()
    except Exception:
        return False


def update_asset_matches(filename: str, system: str) -> bool:
    name = (filename or "").lower()
    if not name.startswith("kumoroute-"):
        return False
    if system == "windows":
        return name.endswith(("-setup.exe", ".zip"))
    if system == "darwin":
        return name.endswith(".dmg")
    if system == "linux":
        return name.endswith((".appimage", ".deb"))
    return False


MIRROR_RELEASE_URL = "http://129.204.149.106/downloads/release.json"


def _fetch_trace(proxy_url: str | None, timeout: int = 8) -> tuple[str, str] | None:
    """Return (ip, country) from Cloudflare's trace endpoint."""
    try:
        if proxy_url:
            handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(handler)
        else:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request("https://1.1.1.1/cdn-cgi/trace", headers={"User-Agent": SUB_UA})
        with opener.open(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except Exception:
        return None
    ip = loc = ""
    for line in body.splitlines():
        if line.startswith("ip="):
            ip = line[3:].strip()
        elif line.startswith("loc="):
            loc = line[3:].strip()
    return (ip, loc) if ip else None


def safe_update_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() == "https":
        trusted = host in {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
    elif parsed.scheme.lower() == "http":
        # Mainland fallback is HTTP-only; integrity comes from SHA256SUMS.txt.
        trusted = host in {"kumoroute.cypilu.cloud", "129.204.149.106"}
    else:
        trusted = False
    return trusted and not parsed.username and not parsed.password


def parse_sha256sums(text: str, filename: str) -> str | None:
    wanted = Path(filename or "").name
    for line in (text or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            digest = parts[0].lstrip("*").lower()
            if parts[-1].lstrip("*") == wanted and re.fullmatch(r"[0-9a-f]{64}", digest):
                return digest
    return None


VPN_REGISTRY_KEY = r"SYSTEM\CurrentControlSet\Services\RasMan\Parameters\Config\VpnCostedNetworkSettings"
VPN_ADVANCED_VALUES = {
    "metered": "NoCostedNetwork",
    "roaming": "NoRoamingNetwork",
}

VPN_POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = @()
$items += Get-VpnConnection
$items += Get-VpnConnection -AllUserConnection
$advanced = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\RasMan\Parameters\Config\VpnCostedNetworkSettings'
[pscustomobject]@{
  Connections = @($items | Sort-Object Name -Unique | Select-Object Name,ServerAddress,TunnelType,ConnectionStatus,RememberCredential,AllUserConnection)
  AllowMetered = -not [bool]$advanced.NoCostedNetwork
  AllowRoaming = -not [bool]$advanced.NoRoamingNetwork
} | ConvertTo-Json -Depth 5 -Compress
"""


VPN_CREDENTIAL_PREFIX = "KumoRoute/VPN/"
VPN_RAS_ERRORS = {
    645: "Windows VPN 驗證失敗",
    691: "使用者名稱或密碼錯誤",
    720: "PPP 連線協商失敗",
    809: "VPN 連線逾時或伺服器無回應",
    868: "找不到 VPN 伺服器",
}


class _RasDialParamsW(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("szEntryName", ctypes.c_wchar * 257),
        ("szPhoneNumber", ctypes.c_wchar * 129),
        ("szCallbackNumber", ctypes.c_wchar * 129),
        ("szUserName", ctypes.c_wchar * 257),
        ("szPassword", ctypes.c_wchar * 257),
        ("szDomain", ctypes.c_wchar * 16),
        ("dwSubEntry", ctypes.c_uint32),
        ("dwCallbackId", ctypes.c_size_t),
        ("dwIfIndex", ctypes.c_uint32),
        ("szEncPassword", ctypes.c_void_p),
    ]


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]


class _CredentialW(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FileTime),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


def _vpn_credential_target(name: str) -> str:
    return VPN_CREDENTIAL_PREFIX + str(name or "").strip()


def _advapi32():
    api = ctypes.WinDLL("advapi32")
    api.CredWriteW.argtypes = [ctypes.POINTER(_CredentialW), ctypes.c_uint32]
    api.CredWriteW.restype = ctypes.c_int
    api.CredReadW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(_CredentialW))]
    api.CredReadW.restype = ctypes.c_int
    api.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    api.CredDeleteW.restype = ctypes.c_int
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def _vpn_credential_read(name: str) -> dict | None:
    api = _advapi32()
    target = _vpn_credential_target(name)
    credential = ctypes.POINTER(_CredentialW)()
    if not api.CredReadW(target, 1, 0, ctypes.byref(credential)) or not credential:
        return None
    try:
        item = credential.contents
        raw = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        return {
            "username": str(item.UserName or ""),
            "password": raw.decode("utf-16-le", "replace"),
        }
    finally:
        api.CredFree(ctypes.cast(credential, ctypes.c_void_p))


def _vpn_credential_write(name: str, username: str, password: str) -> bool:
    api = _advapi32()
    blob = password.encode("utf-16-le")
    buffer = ctypes.create_string_buffer(blob)
    item = _CredentialW()
    item.Type = 1
    item.TargetName = _vpn_credential_target(name)
    item.CredentialBlobSize = len(blob)
    item.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    item.Persist = 2
    item.UserName = str(username or "")
    return bool(api.CredWriteW(ctypes.byref(item), 0))


def _vpn_credential_delete(name: str) -> None:
    try:
        _advapi32().CredDeleteW(_vpn_credential_target(name), 1, 0)
    except Exception:
        pass


VPN_TUNNEL_TYPES = {"pptp": "Pptp", "l2tp": "L2tp", "ikev2": "Ikev2", "sstp": "Sstp", "automatic": "Automatic"}


def _ps_quote(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _vpn_profile_command(script: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference='Stop'; " + script],
            capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return True, ""
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"PowerShell 結束代碼 {result.returncode}"
    except Exception as exc:
        return False, str(exc)


def _vpn_tunnel(value: str) -> str:
    return VPN_TUNNEL_TYPES.get(str(value or "").strip().lower(), "")


def _vpn_ras_disconnect(name: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["rasdial.exe", name, "/disconnect"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return True, ""
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"VPN 斷線失敗（代碼 {result.returncode}）"
    except Exception as exc:
        return False, str(exc)


def _vpn_ras_dial(name: str, username: str, password: str) -> tuple[int, str]:
    api = ctypes.WinDLL("rasapi32")
    api.RasDialW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(_RasDialParamsW), ctypes.c_uint32,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    api.RasDialW.restype = ctypes.c_uint32
    api.RasHangUpW.argtypes = [ctypes.c_void_p]
    api.RasHangUpW.restype = ctypes.c_uint32
    params = _RasDialParamsW()
    params.dwSize = ctypes.sizeof(params)
    params.szEntryName = name
    params.szUserName = username
    params.szPassword = password
    connection = ctypes.c_void_p()
    code = int(api.RasDialW(None, None, ctypes.byref(params), 0, None, ctypes.byref(connection)))
    if code:
        if connection.value:
            api.RasHangUpW(connection)
        return code, VPN_RAS_ERRORS.get(code, f"VPN 連線失敗（錯誤 {code}）")
    return 0, ""


DEFAULT_SETTINGS = {
    "mixed_port": 7890,
    "controller_port": 9090,
    "mode": "rule",
    "active_profile": "",
    "original_proxy": None,
    "vpn_disable_system_proxy": True,
    "vpn_restore_system_proxy": True,
    "vpn_proxy_pending": False,
    "network_mode": "coexist",
    "force_disable_ipv6": False,
    "dns_mode": "auto",
    "subscription_update_hours": 0,
    "last_subscription_update": "",
}


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


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
            _atomic_write_text(self.path, json.dumps(self.data, ensure_ascii=False, indent=2))


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


def recover_stale_proxy(store: Store) -> dict | None:
    """Restore the pre-KumoRoute proxy left behind by an unclean shutdown."""
    if sys.platform != "win32":
        return None
    original = store.data.get("original_proxy")
    if not original:
        return None
    current = get_system_proxy()
    expected = f"127.0.0.1:{int(store.data.get('mixed_port', 7890))}"
    if current.get("enable") == 1 and str(current.get("server", "")).strip() == expected:
        try:
            _apply_registry_proxy(
                int(original.get("enable", 0)),
                str(original.get("server", "")),
                str(original.get("override", "")),
            )
        except Exception as exc:
            return {"attempted": True, "restored": False, "error": str(exc)}
        store.data["original_proxy"] = None
        try:
            store.save()
        except Exception as exc:
            return {
                "attempted": True,
                "restored": True,
                "error": f"代理已恢復，但設定檔儲存失敗：{exc}",
            }
        return {"attempted": True, "restored": True}
    store.data["original_proxy"] = None
    try:
        store.save()
    except Exception as exc:
        return {
            "attempted": True,
            "cleared_stale": True,
            "error": f"已忽略過期代理快照，但設定檔儲存失敗：{exc}",
        }
    return {"attempted": True, "cleared_stale": True}


class Profiles:
    def __init__(self, store: Store, root: Path | None = None):
        self._store = store
        self.root = Path(root) if root else data_dir() / "profiles"
        self.root.mkdir(parents=True, exist_ok=True)
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
        _atomic_write_text(self.index_path, json.dumps(self.entries, ensure_ascii=False, indent=2))

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
    def _validate_remote_url(url: str) -> urllib.parse.ParseResult:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            raise ValueError("訂閱連結必須是有效的 http(s):// 網址")
        if parsed.username or parsed.password:
            raise ValueError("訂閱連結不可包含帳號或密碼")
        return parsed

    @staticmethod
    def _fetch(url: str) -> str:
        req = urllib.request.Request(
            url, headers={"User-Agent": SUB_UA, "Accept": "*/*"}
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            content_length = r.headers.get("Content-Length")
            try:
                declared_size = int(content_length) if content_length else 0
            except (TypeError, ValueError):
                declared_size = 0
            if declared_size > 10 * 1024 * 1024:
                raise ValueError("訂閱檔案超過 10MB，已中止")
            raw = r.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("訂閱檔案超過 10MB，已中止")
        return raw.decode("utf-8", "replace")

    def _register_entry(self, entry: dict, text: str) -> dict:
        path = self.path_of(entry["id"])
        _atomic_write_text(path, text)
        try:
            with self.lock:
                self.entries.append(entry)
                self._save()
        except Exception:
            with self.lock:
                self.entries = [e for e in self.entries if e["id"] != entry["id"]]
            path.unlink(missing_ok=True)
            raise
        return entry

    def add_remote(self, url: str, name: str) -> dict:
        url = (url or "").strip()
        parsed = self._validate_remote_url(url)
        text = self._fetch(url)
        self._validate(text)
        pid = uuid.uuid4().hex[:8]
        entry = {
            "id": pid,
            "name": (name or "").strip() or parsed.hostname or f"訂閱 {len(self.entries) + 1}",
            "kind": "remote",
            "url": url,
            "updated_at": _now(),
        }
        return self._register_entry(entry, text)

    def add_local(self, src: str) -> dict:
        p = Path(src)
        text = p.read_text(encoding="utf-8", errors="replace")
        self._validate(text)
        entry = {
            "id": uuid.uuid4().hex[:8],
            "name": p.stem,
            "kind": "local",
            "url": "",
            "updated_at": _now(),
        }
        return self._register_entry(entry, text)

    def _backup_path_of(self, pid: str) -> Path:
        return self.root / f"{pid}.yaml.bak"

    def _apply_remote_text(self, pid: str, text: str) -> dict:
        self._validate(text)
        entry = self.get(pid)
        if not entry:
            raise ValueError("找不到該訂閱")
        if entry["kind"] != "remote" or not entry.get("url"):
            raise ValueError("只有遠端訂閱可以更新")
        path = self.path_of(pid)
        backup = self._backup_path_of(pid)
        previous = dict(entry)
        backup.write_bytes(path.read_bytes())
        try:
            _atomic_write_text(path, text)
            entry["updated_at"] = _now()
            with self.lock:
                self._save()
        except Exception as exc:
            try:
                _atomic_write_text(path, backup.read_text(encoding="utf-8"))
            finally:
                entry.clear()
                entry.update(previous)
            raise ValueError(f"訂閱更新失敗，已自動回滾：{exc}") from exc
        return entry

    def update(self, pid: str) -> dict:
        entry = self.get(pid)
        if not entry:
            raise ValueError("找不到該訂閱")
        if entry["kind"] != "remote" or not entry.get("url"):
            raise ValueError("只有遠端訂閱可以更新")
        self._validate_remote_url(entry["url"])
        text = self._fetch(entry["url"])
        return self._apply_remote_text(pid, text)

    def rollback_to(self, pid: str, previous: dict) -> None:
        backup = self._backup_path_of(pid)
        if not backup.is_file():
            raise ValueError("找不到可回滾的訂閱備份")
        text = backup.read_text(encoding="utf-8")
        self._validate(text)
        _atomic_write_text(self.path_of(pid), text)
        entry = self.get(pid)
        if entry is not None:
            entry.clear()
            entry.update(previous)
        with self.lock:
            self._save()

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
            self._backup_path_of(pid).unlink(missing_ok=True)
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
        if self._store.data.get("force_disable_ipv6") or ("ipv6" not in cfg and not _has_global_ipv6()):
            cfg["ipv6"] = False
        elif "ipv6" not in cfg:
            cfg["ipv6"] = True
        if self._store.data.get("dns_mode") == "backup":
            dns = cfg.get("dns")
            if not isinstance(dns, dict):
                dns = {}
            dns["enable"] = True
            dns["nameserver"] = ["223.5.5.5", "119.29.29.29"]
            dns["fallback"] = ["1.1.1.1", "8.8.8.8"]
            cfg["dns"] = dns
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


def _history_delay(proxy: dict) -> tuple[str, int] | None:
    history = proxy.get("history") if isinstance(proxy, dict) else None
    if not isinstance(history, list) or not history:
        return None
    item = history[-1]
    if not isinstance(item, dict):
        return None
    try:
        delay = int(item.get("delay"))
    except (TypeError, ValueError):
        return None
    return str(item.get("time") or ""), max(0, delay)


def _windows_has_global_ipv6() -> bool:
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0' -ErrorAction SilentlyContinue | Measure-Object).Count"],
            capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW,
        )
        return int((out.stdout or "0").strip() or 0) > 0
    except Exception:
        return True


def _has_global_ipv6() -> bool:
    if platform.system().lower() == "windows":
        return _windows_has_global_ipv6()
    try:
        with open("/proc/net/ipv6_route", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 5 and parts[0].lower().lstrip("0") == "":
                    return True
    except OSError:
        return True
    return False


def _proxy_last_delay(proxy: dict) -> int | None:
    item = _proxy_last_delay_item(proxy)
    return None if item is None else item[1]


def _proxy_last_delay_item(proxy: dict) -> tuple[str, int] | None:
    candidates = []
    direct = _history_delay(proxy)
    if direct:
        candidates.append(direct)
    extra = proxy.get("extra") if isinstance(proxy, dict) else None
    if isinstance(extra, dict):
        for value in extra.values():
            if isinstance(value, dict):
                item = _history_delay(value)
                if item:
                    candidates.append(item)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])


def _test_ipv6_connectivity() -> bool:
    probe = None
    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        probe.settimeout(2.5)
        probe.connect(("2606:4700:4700::1111", 443))
        return True
    except OSError:
        return False
    finally:
        try:
            probe.close()
        except Exception:
            pass


def _probe_http(proxy_url: str | None = None, timeout: float = 10.0) -> dict:
    started = time.monotonic()
    try:
        handlers = [urllib.request.ProxyHandler({})] if not proxy_url else [
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        ]
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(TEST_URL, headers={"User-Agent": SUB_UA})
        with opener.open(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
        latency = round((time.monotonic() - started) * 1000)
        return {"ok": 200 <= status < 400, "status": status, "latency_ms": latency, "error": "" if 200 <= status < 400 else f"HTTP {status}"}
    except Exception as exc:
        return {"ok": False, "status": 0, "latency_ms": round((time.monotonic() - started) * 1000), "error": str(exc)}


def _system_dns_servers() -> list[str]:
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
             "Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ServerAddresses -Unique"],
            capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW,
        )
        return sorted({line.strip() for line in (out.stdout or "").splitlines() if line.strip()})
    except Exception:
        return []


def _dns_query_txt(name: str, server: str, timeout: float = 4.0) -> str:
    query_id = os.urandom(2)
    labels = [part.encode("idna") for part in name.rstrip(".").split(".") if part]
    question = b"".join(bytes([len(label)]) + label for label in labels) + b"\x00\x00\x10\x00\x01"
    packet = query_id + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + question
    try:
        family = socket.AF_INET6 if ":" in server else socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (server, 53))
            data, _ = sock.recvfrom(4096)
        if len(data) < 12:
            return ""
        qd = int.from_bytes(data[4:6], "big")
        an = int.from_bytes(data[6:8], "big")
        pos = 12
        for _ in range(qd):
            while pos < len(data):
                size = data[pos]
                pos += 1
                if size == 0:
                    break
                pos += size
            pos += 4
        for _ in range(an):
            if pos >= len(data):
                break
            if data[pos] & 0xC0 == 0xC0:
                pos += 2
            else:
                while pos < len(data):
                    size = data[pos]
                    pos += 1
                    if size == 0:
                        break
                    pos += size
            if pos + 10 > len(data):
                break
            rtype = int.from_bytes(data[pos:pos + 2], "big")
            rdlength = int.from_bytes(data[pos + 8:pos + 10], "big")
            pos += 10
            rdata = data[pos:pos + rdlength]
            pos += rdlength
            if rtype == 16 and rdata:
                chunks = []
                p2 = 0
                while p2 < len(rdata):
                    size = rdata[p2]
                    p2 += 1
                    chunks.append(rdata[p2:p2 + size])
                    p2 += size
                return b"".join(chunks).decode("utf-8", "replace")
    except Exception:
        return ""
    return ""


def _first_ip(value: str) -> str:
    """Extract the first valid IP from a DNS TXT value such as Google's resolver token."""
    for candidate in re.findall(r"[0-9A-Fa-f:.]+", str(value or "")):
        try:
            return str(ipaddress.ip_address(candidate.strip(" .")))
        except ValueError:
            continue
    return ""


def _fetch_egress_ip(proxy_url: str | None = None, timeout: float = 8.0) -> str:
    try:
        handlers = [urllib.request.ProxyHandler({})] if not proxy_url else [
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        ]
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request("https://1.1.1.1/cdn-cgi/trace", headers={"User-Agent": SUB_UA})
        with opener.open(request, timeout=timeout) as response:
            body = response.read(8192).decode("utf-8", "replace")
        for line in body.splitlines():
            if line.startswith("ip="):
                return line[3:].strip()
    except Exception:
        pass
    return ""


def _doh_template_count() -> int:
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-DnsClientDohServerAddress -ErrorAction SilentlyContinue | Measure-Object).Count"],
            capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW,
        )
        return int((out.stdout or "0").strip() or 0)
    except Exception:
        return 0


def _configured_dns_protocols(profiles) -> tuple[int, int]:
    """Count DoH/DoT resolvers configured by the active profile."""
    doh = 0
    dot = 0
    try:
        entry = profiles.active_entry()
        path = profiles.path_of(entry["id"])
        if not hasattr(path, "read_text"):
            path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        cfg = yaml.safe_load(text) or {}
        dns = cfg.get("dns") if isinstance(cfg, dict) else None
        values: list[str] = []

        def walk(value):
            if isinstance(value, str):
                values.append(value.strip().lower())
            elif isinstance(value, dict):
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, (list, tuple)):
                for nested in value:
                    walk(nested)

        walk(dns)
        doh = sum(1 for value in values if value.startswith(("https://", "quic://")))
        dot = sum(1 for value in values if value.startswith("tls://"))
    except Exception:
        pass
    return doh, dot


def _merge_network_issue(issues: list[dict], kind: str, count: int, message: str) -> None:
    existing = next((item for item in issues if item.get("type") == kind), None)
    if existing:
        existing["count"] = int(existing.get("count", 0)) + max(1, count)
        existing["message"] = message
    else:
        issues.append({"type": kind, "count": max(1, count), "message": message})


def _group_network_issues(lines: list[str]) -> list[dict]:
    buckets = {
        "ipv6": {"type": "ipv6", "count": 0, "message": "IPv6 連線不可達"},
        "dns": {"type": "dns", "count": 0, "message": "DNS 解析失敗"},
        "timeout": {"type": "timeout", "count": 0, "message": "連線逾時"},
    }
    for line in lines:
        low = line.lower()
        ipv6_text = "ipv6" in low or "unreachable network" in low
        network_error = any(word in low for word in (
            "error", "fail", "unreachable", "timeout", "deadline exceeded", "refused",
        ))
        if ipv6_text and network_error:
            buckets["ipv6"]["count"] += 1
        if "dns" in low and network_error:
            buckets["dns"]["count"] += 1
        if "timeout" in low or "deadline exceeded" in low:
            buckets["timeout"]["count"] += 1
    return [item for item in buckets.values() if item["count"] > 0]


class Api:
    def __init__(self, store: Store, profiles: Profiles, core: Core):
        self._store = store
        self._profiles = profiles
        self._core = core
        self._win = None
        self._on_quit = None
        self._proxy_recovery = None
        self._update_lock = threading.Lock()
        self._update_cancel = threading.Event()
        self._update_status = {
            "active": False,
            "phase": "idle",
            "received": 0,
            "total": 0,
            "percent": 0,
            "path": None,
            "error": None,
        }

    # ---- state ----

    def _public_entry(self, entry: dict | None) -> dict | None:
        if not entry:
            return None
        return {k: entry.get(k, "") for k in ("id", "name", "kind", "updated_at")}

    def get_state(self) -> dict:
        recovery = self._proxy_recovery
        self._proxy_recovery = None
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
            "network_mode": self._store.data.get("network_mode", "coexist"),
            "subscription_update_hours": int(self._store.data.get("subscription_update_hours", 0) or 0),
            "last_subscription_update": str(self._store.data.get("last_subscription_update") or ""),
            "proxy_recovery": recovery,
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
        was_enabled = is_system_proxy_on(self._store)
        try:
            if enabled:
                if not self._core.is_up():
                    ok, msg = self._core.start()
                    if not ok:
                        return {"ok": False, "error": "核心啟動失敗：" + msg}
                cur = get_system_proxy()
                ours = cur["enable"] == 1 and cur["server"].startswith("127.0.0.1:")
                captured_now = not ours and not self._store.data.get("original_proxy")
                if captured_now:
                    self._store.data["original_proxy"] = cur
                    self._store.save()
                try:
                    _apply_registry_proxy(
                        1,
                        f"127.0.0.1:{int(self._store.data['mixed_port'])}",
                        PROXY_OVERRIDE,
                    )
                except Exception:
                    if captured_now:
                        self._store.data["original_proxy"] = None
                        self._store.save()
                    raise
                self._store.save()
                time.sleep(1.2)
                if not is_system_proxy_on(self._store):
                    if captured_now:
                        self._store.data["original_proxy"] = None
                        self._store.save()
                    return {
                        "ok": False,
                        "error": "系統代理被其他軟體改回（常見於安全軟體／網路加速器的代理守護）。"
                        "請關閉該功能後再試。",
                        "sys_proxy": False,
                    }
                validation = _probe_http(f"http://127.0.0.1:{int(self._store.data['mixed_port'])}", timeout=8)
                if not validation.get("ok"):
                    rollback = self.set_system_proxy(False)
                    restored = bool(rollback.get("ok"))
                    return {
                        "ok": False,
                        "error": ("系統代理已開啟，但實際連線驗證失敗，已自動恢復原本狀態。"
                                  if restored else
                                  "系統代理已開啟，但實際連線驗證失敗，且自動恢復失敗，請檢查系統代理設定。"),
                        "sys_proxy": is_system_proxy_on(self._store),
                        "validation": validation,
                        "rolled_back": restored,
                        "rollback_error": "" if restored else str(rollback.get("error") or "未知錯誤"),
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
            result = {"ok": True, "sys_proxy": is_system_proxy_on(self._store)}
            if enabled:
                result["validation"] = validation
            elif was_enabled:
                result["rolled_back"] = False
            return result
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
                    delay_item = _proxy_last_delay_item(np)
                    nodes.append({
                        "name": n,
                        "type": np.get("type", ""),
                        "delay": delay_item[1] if delay_item else None,
                        "delay_updated_at": delay_item[0] if delay_item else "",
                    })
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

    def test_node_delay(self, name: str) -> dict:
        name = str(name or "").strip()
        if not name:
            return {"ok": False, "error": "找不到該節點"}
        try:
            res = self._core.api(
                "GET",
                f"/proxies/{quote(name, safe='')}/delay"
                f"?timeout=5000&url={quote(TEST_URL, safe='')}",
                timeout=12,
            )
            delay = int((res or {}).get("delay") or 0)
            return {"ok": True, "name": name, "delay": delay}
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

    def set_subscription_auto_update(self, hours: int) -> dict:
        hours = int(hours)
        if hours not in (0, 6, 12, 24):
            return {"ok": False, "error": "無效的自動更新間隔"}
        self._store.data["subscription_update_hours"] = hours
        self._store.save()
        return {"ok": True, "hours": hours}

    def subscription_auto_update(self, force: bool = False) -> dict:
        hours = int(self._store.data.get("subscription_update_hours", 0) or 0)
        if hours <= 0:
            return {"ok": True, "skipped": True, "reason": "disabled", "updated": 0, "failed": []}
        last_text = str(self._store.data.get("last_subscription_update") or "")
        if not force and last_text:
            try:
                last = datetime.fromisoformat(last_text)
                if (datetime.now() - last).total_seconds() < hours * 3600:
                    return {"ok": True, "skipped": True, "reason": "not_due", "updated": 0, "failed": []}
            except ValueError:
                pass
        updated = []
        previous_entries = []
        failed = []
        rolled_back = []
        remote_entries = [entry for entry in list(self._profiles.entries) if entry.get("kind") == "remote"]
        for entry in remote_entries:
            previous = dict(entry)
            try:
                self._profiles.update(entry["id"])
                previous_entries.append((entry["id"], previous))
                updated.append(entry.get("name") or entry["id"])
            except Exception as exc:
                failed.append({"name": entry.get("name") or entry["id"], "error": str(exc)})
        reload_failed = False
        if updated:
            try:
                ok, message = self._core.reload_runtime()
            except Exception as exc:
                ok, message = False, str(exc)
            if not ok:
                reload_failed = True
                failed.append({"name": "核心重新載入", "error": message})
                for pid, previous in reversed(previous_entries):
                    try:
                        self._profiles.rollback_to(pid, previous)
                        rolled_back.append(previous.get("name") or pid)
                    except Exception as exc:
                        failed.append({"name": f"回滾 {previous.get('name') or pid}", "error": str(exc)})
                if rolled_back:
                    try:
                        self._core.reload_runtime()
                    except Exception:
                        pass
        if updated or not remote_entries:
            self._store.data["last_subscription_update"] = datetime.now().isoformat()
        self._store.save()
        return {
            "ok": True,
            "skipped": False,
            "updated": len(updated),
            "names": updated,
            "failed": failed,
            "rolled_back": rolled_back,
            "reload_failed": reload_failed,
            "checked_at": self._store.data["last_subscription_update"],
        }

    def export_backup(self) -> dict:
        try:
            folder = Path.home() / "Downloads"
            if not folder.is_dir():
                folder = data_dir()
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"KumoRoute-backup-{datetime.now():%Y%m%d-%H%M%S}.json"
            path.write_text(json.dumps(self._backup_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
            return {"ok": True, "path": str(path)}
        except Exception as exc:
            return {"ok": False, "error": f"建立備份失敗：{exc}"}

    def import_backup(self) -> dict:
        return {'ok': False, 'error': 'not implemented'}

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
            previous = self._profiles.get(pid)
            previous = dict(previous) if previous else None
            self._profiles.update(pid)
            if self._store.data.get("active_profile") == pid:
                ok, msg = self._core.reload_runtime()
                if not ok:
                    if previous:
                        self._profiles.rollback_to(pid, previous)
                        self._core.reload_runtime()
                    return {"ok": False, "error": f"更新失敗，已自動回滾：{msg}"}
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
            deduped = []
            last_key = None
            for ln in lines:
                key = re.sub(r"(?:\d+\.\d+\.\d+\.\d+|\[[0-9a-f:]+\])", "<addr>", ln)
                key = re.sub(r"\d{4}-\d{2}-\d{2}T[^ ]+", "<time>", key)
                if key == last_key:
                    if deduped:
                        deduped[-1] = ln
                    else:
                        deduped.append(ln)
                else:
                    deduped.append(ln)
                    last_key = key
            return {"ok": True, "lines": deduped[-300:]}
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

    def check_update(self) -> dict:
        release = None
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/cypwlp/kumoroute/releases/latest",
                headers={"User-Agent": SUB_UA, "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=12) as r:
                release = json.load(r)
        except Exception:
            release = None
        if not isinstance(release, dict) or not release.get("tag_name"):
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(MIRROR_RELEASE_URL, headers={"User-Agent": SUB_UA}),
                    timeout=8,
                ) as r:
                    mirrored = json.load(r)
                if isinstance(mirrored, dict) and mirrored.get("tag_name"):
                    release = mirrored
            except Exception:
                release = None
        if not isinstance(release, dict) or not release.get("tag_name"):
            return {"ok": False, "error": "檢查更新失敗：GitHub 與大陸鏡像皆無法連線"}
        try:
            latest = str(release.get("tag_name") or "").lstrip("v")
            current = APP_VERSION.lstrip("v")

            def version_key(value: str) -> tuple[int, ...]:
                nums = [int(x) for x in re.findall(r"\d+", value)]
                return tuple(nums + [0] * (4 - len(nums)))[:4]

            return {
                "ok": True,
                "current": current,
                "latest": latest,
                "update_available": version_key(latest) > version_key(current),
                "url": str(release.get("html_url") or "https://github.com/cypwlp/kumoroute/releases/latest"),
                "published_at": str(release.get("published_at") or ""),
                "notes": str(release.get("body") or "")[:4000],
                "asset": self._update_asset(release, is_portable_build()),
                "install_mode": "portable" if is_portable_build() else "installed",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def _update_asset(release: dict, prefer_zip: bool = False) -> dict | None:
        assets = release.get("assets") if isinstance(release.get("assets"), list) else []
        clean = []
        checksum_url = ""
        for item in assets:
            if not isinstance(item, dict):
                continue
            name = Path(str(item.get("name") or "")).name
            url = str(item.get("browser_download_url") or "")
            if not name or not safe_update_url(url):
                continue
            clean.append({
                "filename": name,
                "download_url": url,
                "size": int(item.get("size") or 0),
            })
            if name == "SHA256SUMS.txt":
                checksum_url = url
        system = platform.system().lower()
        matches = [item for item in clean if update_asset_matches(item["filename"], system)]
        if system == "windows":
            if prefer_zip:
                matches.sort(key=lambda item: 0 if item["filename"].lower().endswith(".zip") else 1)
            else:
                matches.sort(key=lambda item: 0 if item["filename"].lower().endswith("-setup.exe") else 1)
        selected = matches[0] if matches else None
        if selected is None:
            return None
        return {
            "filename": selected["filename"],
            "download_url": selected["download_url"],
            "size": selected["size"],
            "size_mb": round(selected["size"] / 1048576, 1),
            "sha256_url": checksum_url,
        }

    def _update_status_snapshot(self) -> dict:
        lock = getattr(self, "_update_lock", None)
        status = getattr(self, "_update_status", {})
        if lock:
            with lock:
                return dict(status)
        return dict(status)

    def _set_update_status(self, **updates) -> dict:
        lock = getattr(self, "_update_lock", None)
        if lock:
            with lock:
                self._update_status.update(updates)
                return dict(self._update_status)
        return dict(updates)

    def _perform_update_download(
        self,
        url: str,
        filename: str,
        sha256_url: str = "",
        cancel_event: threading.Event | None = None,
        progress=None,
    ) -> Path:
        if not safe_update_url(url) or not safe_update_url(sha256_url):
            raise ValueError("不安全的更新下載網址")
        safe_name = Path(filename or "").name
        if not safe_name or not update_asset_matches(safe_name, platform.system().lower()):
            raise ValueError("更新檔名或平台不相符")
        folder = Path.home() / "Downloads"
        if not folder.is_dir():
            folder = data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / safe_name
        partial = destination.with_name(destination.name + ".part")
        if progress:
            progress(0, 0, "verifying")
        with urllib.request.urlopen(urllib.request.Request(sha256_url, headers={"User-Agent": SUB_UA}), timeout=30) as response:
            sums = response.read(128 * 1024).decode("utf-8", "replace")
        expected = parse_sha256sums(sums, safe_name)
        if not expected:
            raise ValueError("找不到更新檔的 SHA256 校驗值")
        request = urllib.request.Request(url, headers={"User-Agent": SUB_UA})
        with urllib.request.urlopen(request, timeout=120) as response:
            status = int(getattr(response, "status", 200))
            if status < 200 or status >= 300:
                raise ValueError(f"更新伺服器回應 HTTP {status}")
            total = int(response.headers.get("Content-Length") or 0)
            if total <= 0 or total > 700 * 1024 * 1024:
                raise ValueError("更新檔大小無效或超過安全上限")
            digest = hashlib.sha256()
            written = 0
            last_report = 0.0
            if progress:
                progress(0, total, "downloading")
            with partial.open("wb") as handle:
                while True:
                    if cancel_event and cancel_event.is_set():
                        raise ValueError("更新下載已取消")
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > total:
                        raise ValueError("更新檔大小超出宣告值")
                    digest.update(chunk)
                    handle.write(chunk)
                    now = time.monotonic()
                    if progress and (written == total or now - last_report >= 0.15):
                        progress(written, total, "downloading")
                        last_report = now
            if written != total:
                raise ValueError("更新檔下載不完整")
            if progress:
                progress(written, total, "verifying")
            if digest.hexdigest().lower() != expected:
                raise ValueError("更新檔 SHA256 校驗失敗")
            partial.replace(destination)
        return destination

    def install_update(self, url: str, filename: str, sha256_url: str = "") -> dict:
        try:
            destination = self._perform_update_download(url, filename, sha256_url)
            return {"ok": True, "path": str(destination), "filename": destination.name}
        except Exception as exc:
            try:
                partial = (Path.home() / "Downloads" / Path(filename or "").name).with_name(Path(filename or "").name + ".part")
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            return {"ok": False, "error": f"下載更新失敗：{exc}"}

    def start_update_download(self, url: str, filename: str, sha256_url: str = "") -> dict:
        if self._update_status_snapshot().get("active"):
            return {"ok": False, "error": "已有更新正在下載"}
        self._update_cancel.clear()
        status = self._set_update_status(active=True, phase="verifying", received=0, total=0, percent=0, path=None, error=None)

        def progress(received, total, phase):
            percent = round((received / total) * 100) if total else 0
            self._set_update_status(
                active=phase in ("downloading", "verifying"),
                phase=phase,
                received=received,
                total=total,
                percent=min(100, percent),
            )

        def worker():
            try:
                destination = self._perform_update_download(url, filename, sha256_url, self._update_cancel, progress)
                self._set_update_status(active=False, phase="complete", percent=100, path=str(destination), error=None)
            except Exception as exc:
                phase = "cancelled" if self._update_cancel.is_set() else "error"
                self._set_update_status(active=False, phase=phase, path=None, error=str(exc))

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "started": True, "status": status}

    def update_download_status(self) -> dict:
        return {"ok": True, "status": self._update_status_snapshot()}

    def cancel_update_download(self) -> dict:
        if not self._update_status_snapshot().get("active"):
            return {"ok": True, "cancelled": False}
        self._update_cancel.set()
        return {"ok": True, "cancelled": True}

    def _updates_dir(self) -> Path:
        return data_dir() / "updates"

    def _current_app_paths(self) -> tuple[Path, Path]:
        exe = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
        return exe, exe.parent

    def _create_update_backup(self, target_version: str) -> dict:
        exe, app_dir = self._current_app_paths()
        updates = self._updates_dir()
        backup = updates / "previous"
        if backup.exists():
            shutil.rmtree(backup)
        updates.mkdir(parents=True, exist_ok=True)
        shutil.copytree(app_dir, backup)
        state = {
            "pending": True,
            "completed": False,
            "failed": False,
            "from_version": APP_VERSION,
            "target_version": target_version,
            "backup_dir": str(backup),
            "install_dir": str(app_dir),
            "executable": str(exe),
            "install_mode": "portable" if is_portable_build() else "installed",
            "created_at": _now(),
        }
        (updates / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

    def _launch_update_helper(self, action: str, archive: str, app_dir: str, exe: str, backup: str) -> None:
        updates = self._updates_dir()
        updates.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).with_name("update_helper.ps1")
        if not source.is_file():
            raise ValueError("找不到更新輔助程式")
        script = updates / "apply-update.ps1"
        script.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.Popen([
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-Action", action, "-Archive", archive, "-AppDir", app_dir,
            "-Exe", exe, "-Backup", backup,
        ], creationflags=CREATE_NO_WINDOW)

    def get_update_state(self) -> dict:
        path = self._updates_dir() / "state.json"
        try:
            state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except Exception:
            state = {}
        target = str(state.get("target_version") or "")
        pending = bool(state.get("pending"))
        current_key = tuple(int(x) for x in re.findall(r"\d+", APP_VERSION))[:4]
        target_parts = [int(x) for x in re.findall(r"\d+", target)]
        target_key = tuple(target_parts + [0] * (4 - len(target_parts)))[:4] if target else ()
        completed = pending and bool(target_key) and current_key >= target_key
        if completed:
            state["pending"] = False
            state["completed"] = True
            try:
                path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
        backup = self._updates_dir() / "previous"
        return {
            "ok": True,
            "current_version": APP_VERSION,
            "install_mode": "portable" if is_portable_build() else "installed",
            "backup_available": backup.is_dir(),
            "previous_version": str(state.get("from_version") or ""),
            "target_version": target,
            "pending": bool(state.get("pending")),
            "failed": bool(state.get("pending")) and (not target_key or current_key < target_key),
            "completed": bool(state.get("completed")),
            "created_at": str(state.get("created_at") or ""),
            "backup_dir": str(backup),
        }

    def rollback_update(self) -> dict:
        state = self.get_update_state()
        if not state.get("backup_available"):
            return {"ok": False, "error": "找不到上一版備份"}
        path = self._updates_dir() / "state.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except Exception:
            raw = {}
        app_dir = str(raw.get("install_dir") or "")
        exe = str(raw.get("executable") or "")
        if not app_dir or not exe:
            return {"ok": False, "error": "更新備份資訊不完整"}
        try:
            self._launch_update_helper("rollback", "", app_dir, exe, str(self._updates_dir() / "previous"))
            threading.Thread(target=self._quit_after_update, daemon=True).start()
            return {"ok": True, "rollback_started": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def run_update_installer(self, path: str, target_version: str = "") -> dict:
        try:
            target = Path(path).resolve()
            allowed_roots = [(Path.home() / "Downloads").resolve(), data_dir().resolve()]
            if not any(target.parent == root for root in allowed_roots) or not target.is_file():
                return {"ok": False, "error": "更新安裝檔位置不安全或不存在"}
            suffix = target.suffix.lower()
            if suffix == ".zip":
                if not is_portable_build():
                    return {"ok": False, "error": "ZIP 更新只適用於免安裝版"}
                backup = self._create_update_backup(target_version)
                self._launch_update_helper(
                    "portable", str(target), backup["install_dir"],
                    backup["executable"], backup["backup_dir"],
                )
            elif platform.system().lower() == "windows" and suffix == ".exe":
                self._create_update_backup(target_version)
                subprocess.Popen(
                    [str(target), "/P", "/UPDATE", "/R"],
                    cwd=str(target.parent),
                )
            elif platform.system().lower() == "darwin" and suffix == ".dmg":
                subprocess.Popen(["open", str(target)])
            elif platform.system().lower() == "linux" and suffix in (".appimage", ".deb"):
                subprocess.Popen(["xdg-open", str(target)])
            else:
                return {"ok": False, "error": "不支援的更新安裝檔格式"}
            threading.Thread(target=self._quit_after_update, daemon=True).start()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _quit_after_update(self) -> None:
        time.sleep(0.8)
        if self._on_quit:
            self._on_quit()

    def _vpn_settings(self) -> dict:
        store = getattr(self, "_store", None)
        data = store.data if store else {}
        return {
            "disable_system_proxy": bool(data.get("vpn_disable_system_proxy", True)),
            "restore_system_proxy": bool(data.get("vpn_restore_system_proxy", True)),
            "network_mode": data.get("network_mode", "coexist"),
        }

    def vpn_list(self) -> dict:
        if platform.system().lower() != "windows":
            return {
                "ok": True,
                "supported": False,
                "connections": [],
                "advanced": {"allow_metered": True, "allow_roaming": True},
                "settings": self._vpn_settings(),
            }
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", VPN_POWERSHELL_SCRIPT],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=CREATE_NO_WINDOW,
            )
            raw = (result.stdout or "").strip()
            if not raw:
                detail = (result.stderr or "").strip()
                if result.returncode != 0:
                    raise RuntimeError(detail or f"PowerShell 結束代碼 {result.returncode}")
                return {
                    "ok": True,
                    "supported": True,
                    "connections": [],
                    "advanced": {"allow_metered": True, "allow_roaming": True},
                    "settings": self._vpn_settings(),
                }

            data = json.loads(raw)
            if isinstance(data, list):
                items = data
                advanced = {"allow_metered": True, "allow_roaming": True}
            elif isinstance(data, dict):
                items = data.get("Connections") or []
                if isinstance(items, dict):
                    items = [items]
                advanced = {
                    "allow_metered": bool(data.get("AllowMetered", True)),
                    "allow_roaming": bool(data.get("AllowRoaming", True)),
                }
            else:
                items = []
                advanced = {"allow_metered": True, "allow_roaming": True}

            connections = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("Name") or "").strip()
                if not name:
                    continue
                status = str(item.get("ConnectionStatus") or "Disconnected").strip()
                try:
                    credential = _vpn_credential_read(name)
                except Exception:
                    credential = None
                connections.append({
                    "name": name,
                    "server": str(item.get("ServerAddress") or ""),
                    "type": str(item.get("TunnelType") or ""),
                    "status": status,
                    "connected": status.lower() == "connected",
                    "remember_credential": bool(item.get("RememberCredential")),
                    "all_user": bool(item.get("AllUserConnection")),
                    "credential_saved": credential is not None,
                    "saved_username": credential.get("username", "") if credential else "",
                })
            connections.sort(key=lambda item: (not item["connected"], item["name"].lower()))
            return {
                "ok": True,
                "supported": True,
                "connections": connections,
                "advanced": advanced,
                "settings": self._vpn_settings(),
            }
        except Exception as exc:
            return {
                "ok": False,
                "supported": True,
                "connections": [],
                "advanced": {"allow_metered": True, "allow_roaming": True},
                "settings": self._vpn_settings(),
                "error": f"讀取 Windows VPN 失敗：{exc}",
            }

    def list_vpn_connections(self) -> dict:
        return self.vpn_list()

    def _vpn_profile(self, name: str) -> dict | None:
        result = self.vpn_list()
        if not result.get("ok"):
            return None
        wanted = str(name or "").strip().lower()
        return next((item for item in result.get("connections", []) if item["name"].lower() == wanted), None)

    def _vpn_prepare_proxy(self) -> dict | None:
        store = getattr(self, "_store", None)
        if not store or not store.data.get("vpn_disable_system_proxy", True):
            return None
        if not is_system_proxy_on(store):
            return None
        result = self.set_system_proxy(False)
        if not result.get("ok"):
            return {"ok": False, "error": "關閉系統代理失敗：" + str(result.get("error") or "")}
        store.data["vpn_proxy_pending"] = True
        try:
            store.save()
        except Exception as exc:
            app_log(f"VPN proxy pending save failed: {exc}")
        return {"ok": True, "proxy_disabled": True}

    def _vpn_restore_proxy(self) -> bool:
        store = getattr(self, "_store", None)
        if not store or not store.data.get("vpn_proxy_pending"):
            return False
        if not store.data.get("vpn_restore_system_proxy", True):
            store.data["vpn_proxy_pending"] = False
            try:
                store.save()
            except Exception as exc:
                app_log(f"VPN proxy pending clear failed: {exc}")
            return False
        try:
            result = self.set_system_proxy(True)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        if not result.get("ok"):
            app_log(f"VPN proxy restore failed: {result.get('error', 'unknown error')}")
            return False
        store.data["vpn_proxy_pending"] = False
        try:
            store.save()
        except Exception as exc:
            app_log(f"VPN proxy pending clear failed: {exc}")
        return True

    def _vpn_validate_connection(self, profile_name: str, proxy_prepared: bool, baseline: dict) -> dict:
        time.sleep(1.2)
        validation = _probe_http(None, timeout=8)
        if validation.get("ok"):
            return {"ok": True, "connected": True, "validated": True, "validation": validation}
        should_rollback = proxy_prepared or bool(baseline.get("ok"))
        if not should_rollback:
            return {
                "ok": True,
                "connected": True,
                "validated": False,
                "validation": validation,
                "warning": "VPN 已建立，但目前無法完成網路驗證；連線前的網路也不可用，因此未自動斷線。",
            }
        disconnected, disconnect_error = _vpn_ras_disconnect(profile_name)
        proxy_restored = self._vpn_restore_proxy() if proxy_prepared else False
        restore_expected = bool(self._store.data.get("vpn_restore_system_proxy", True))
        proxy_ok = not proxy_prepared or not restore_expected or proxy_restored
        rolled_back = disconnected and proxy_ok
        if disconnected and proxy_ok:
            error = "VPN 已建立，但實際連線驗證失敗，已自動斷線並恢復原本代理狀態。"
        elif disconnected:
            error = "VPN 實際連線驗證失敗，已自動斷線，但系統代理恢復失敗，請手動檢查。"
        else:
            error = "VPN 實際連線驗證失敗，且自動斷線失敗，請手動斷開 VPN。"
        result = {
            "ok": False,
            "connected": not disconnected,
            "rolled_back": rolled_back,
            "disconnected": disconnected,
            "proxy_restored": proxy_restored,
            "validation": validation,
            "baseline": baseline,
            "error": error,
        }
        if disconnect_error:
            result["disconnect_error"] = disconnect_error
        return result

    def vpn_connect(self, name: str) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        profile = self._vpn_profile(name)
        if not profile:
            return {"ok": False, "error": "找不到該 VPN 連線"}
        try:
            credential = _vpn_credential_read(profile["name"])
        except Exception as exc:
            return {"ok": False, "error": f"讀取 Windows VPN 憑證失敗：{exc}"}
        if not credential:
            return {"ok": False, "needs_credentials": True, "username": profile.get("saved_username", "")}
        proxy_prepared = False
        connected = False
        try:
            proxy_result = self._vpn_prepare_proxy()
            if proxy_result and not proxy_result.get("ok"):
                return proxy_result
            proxy_prepared = bool(proxy_result and proxy_result.get("proxy_disabled"))
            baseline = _probe_http(None, timeout=6)
            code, message = _vpn_ras_dial(
                profile["name"], credential["username"], credential["password"]
            )
            if code != 0:
                if proxy_prepared:
                    self._vpn_restore_proxy()
                if code in (645, 691):
                    _vpn_credential_delete(profile["name"])
                    return {
                        "ok": False,
                        "needs_credentials": True,
                        "username": credential["username"],
                        "stale_credentials": True,
                    }
                return {"ok": False, "error": message, "code": code}
            connected = True
            result = self._vpn_validate_connection(profile["name"], proxy_prepared, baseline)
            result["proxy_disabled"] = proxy_prepared
            return result
        except Exception as exc:
            if connected:
                _vpn_ras_disconnect(profile["name"])
            if proxy_prepared:
                self._vpn_restore_proxy()
            return {"ok": False, "error": f"啟動 VPN 連線失敗：{exc}"}

    def vpn_connect_with_credentials(
        self, name: str, username: str, password: str, remember: bool = True
    ) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        profile = self._vpn_profile(name)
        if not profile:
            return {"ok": False, "error": "找不到該 VPN 連線"}
        username = str(username or "").strip()
        password = str(password or "")
        if not username or not password:
            return {"ok": False, "error": "請輸入 VPN 使用者名稱與密碼"}
        proxy_prepared = False
        connected = False
        try:
            proxy_result = self._vpn_prepare_proxy()
            if proxy_result and not proxy_result.get("ok"):
                return proxy_result
            proxy_prepared = bool(proxy_result and proxy_result.get("proxy_disabled"))
            baseline = _probe_http(None, timeout=6)
            code, message = _vpn_ras_dial(profile["name"], username, password)
            if code != 0:
                if proxy_prepared:
                    self._vpn_restore_proxy()
                if code in (645, 691):
                    _vpn_credential_delete(profile["name"])
                    return {
                        "ok": False,
                        "needs_credentials": True,
                        "username": username,
                        "stale_credentials": True,
                    }
                return {"ok": False, "error": message, "code": code}
            connected = True
            credentials_saved = False
            warning = ""
            if remember:
                try:
                    credentials_saved = bool(_vpn_credential_write(profile["name"], username, password))
                except Exception:
                    credentials_saved = False
                if not credentials_saved:
                    warning = "已連線，但無法保存 VPN 憑證"
            else:
                _vpn_credential_delete(profile["name"])
            result = self._vpn_validate_connection(profile["name"], proxy_prepared, baseline)
            result.update({
                "credentials_saved": credentials_saved,
                "proxy_disabled": proxy_prepared,
            })
            if warning and result.get("ok"):
                current_warning = str(result.get("warning") or "")
                result["warning"] = f"{current_warning} {warning}".strip()
            return result
        except Exception as exc:
            if connected:
                _vpn_ras_disconnect(profile["name"])
            if proxy_prepared:
                self._vpn_restore_proxy()
            return {"ok": False, "error": f"啟動 VPN 連線失敗：{exc}"}

    def vpn_disconnect(self, name: str) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        profile = self._vpn_profile(name)
        if not profile:
            return {"ok": False, "error": "找不到該 VPN 連線"}
        ok, message = _vpn_ras_disconnect(profile["name"])
        if not ok:
            return {"ok": False, "error": message}
        restored = self._vpn_restore_proxy()
        return {"ok": True, "disconnected": True, "proxy_restored": restored}

    def vpn_set_advanced(self, setting: str, enabled: bool) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        value_name = VPN_ADVANCED_VALUES.get(str(setting or "").strip().lower())
        if not value_name:
            return {"ok": False, "error": "無效的 VPN 進階設定"}
        data = "0" if bool(enabled) else "1"
        try:
            result = subprocess.run(
                [
                    "reg.exe", "add", VPN_REGISTRY_KEY,
                    "/v", value_name, "/t", "REG_DWORD", "/d", data, "/f",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return {"ok": True, "pending": False}

            elevation_script = (
                "Start-Process -FilePath 'reg.exe' -Verb RunAs -WindowStyle Hidden -Wait "
                f"-ArgumentList @('add','{VPN_REGISTRY_KEY}','/v','{value_name}',"
                f"'/t','REG_DWORD','/d','{data}','/f')"
            )
            subprocess.Popen(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", elevation_script],
                creationflags=CREATE_NO_WINDOW,
            )
            return {
                "ok": True,
                "pending": True,
                "message": "請在 Windows 的 UAC 提示中允許變更。",
            }
        except Exception as exc:
            return {"ok": False, "error": f"更新 VPN 進階設定失敗：{exc}"}

    def vpn_add(self, name: str, server: str, tunnel_type: str) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        name, server = str(name or "").strip(), str(server or "").strip()
        tunnel = _vpn_tunnel(tunnel_type)
        if not name or not server or not tunnel:
            return {"ok": False, "error": "請輸入 VPN 名稱、伺服器與類型"}
        if self._vpn_profile(name):
            return {"ok": False, "error": "已存在同名 VPN 連線"}
        auth = "MsChapv2" if tunnel in ("Pptp", "L2tp") else "Eap"
        script = (
            f"Add-VpnConnection -Name {_ps_quote(name)} -ServerAddress {_ps_quote(server)} "
            f"-TunnelType {_ps_quote(tunnel)} -EncryptionLevel Required "
            f"-AuthenticationMethod {_ps_quote(auth)} -RememberCredential -Force"
        )
        ok, message = _vpn_profile_command(script)
        return {"ok": True, "name": name} if ok else {"ok": False, "error": f"新增 VPN 失敗：{message}"}

    def vpn_edit(self, name: str, server: str, tunnel_type: str) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        name, server = str(name or "").strip(), str(server or "").strip()
        tunnel = _vpn_tunnel(tunnel_type)
        if not name or not server or not tunnel:
            return {"ok": False, "error": "請輸入 VPN 名稱、伺服器與類型"}
        script = (
            f"Set-VpnConnection -Name {_ps_quote(name)} -ServerAddress {_ps_quote(server)} "
            f"-TunnelType {_ps_quote(tunnel)} -RememberCredential $true"
        )
        ok, message = _vpn_profile_command(script)
        return {"ok": True} if ok else {"ok": False, "error": f"修改 VPN 失敗：{message}"}

    def vpn_delete(self, name: str) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        name = str(name or "").strip()
        if not name:
            return {"ok": False, "error": "找不到該 VPN 連線"}
        ok, message = _vpn_profile_command(f"Remove-VpnConnection -Name {_ps_quote(name)} -Force")
        if not ok:
            return {"ok": False, "error": f"刪除 VPN 失敗：{message}"}
        _vpn_credential_delete(name)
        return {"ok": True}

    def vpn_forget_credentials(self, name: str) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        try:
            _vpn_credential_delete(str(name or "").strip())
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": f"刪除 VPN 憑證失敗：{exc}"}

    def vpn_set_auto_proxy(self, enabled: bool) -> dict:
        self._store.data["vpn_disable_system_proxy"] = bool(enabled)
        self._store.save()
        return {"ok": True, "disable_system_proxy": bool(enabled)}

    def vpn_set_restore_proxy(self, enabled: bool) -> dict:
        self._store.data["vpn_restore_system_proxy"] = bool(enabled)
        self._store.save()
        return {"ok": True, "restore_system_proxy": bool(enabled)}

    def set_network_mode(self, mode: str) -> dict:
        mode = str(mode or "").strip().lower()
        if mode not in ("proxy", "vpn", "coexist"):
            return {"ok": False, "error": "無效的網路接管模式"}
        previous_mode = self._store.data.get("network_mode", "coexist")
        try:
            if mode == "vpn" and is_system_proxy_on(self._store):
                result = self.set_system_proxy(False)
                if not result.get("ok"):
                    return result
            elif mode == "proxy":
                failures = []
                listed = self.vpn_list()
                if not listed.get("ok"):
                    return {"ok": False, "error": listed.get("error") or "無法讀取 VPN 連線"}
                for item in listed.get("connections", []):
                    if not item.get("connected"):
                        continue
                    result = self.vpn_disconnect(item["name"])
                    if not result.get("ok"):
                        failures.append(f"{item['name']}：{result.get('error') or '斷線失敗'}")
                if failures:
                    return {"ok": False, "error": "無法切換到只用代理：" + "；".join(failures)}
                if not is_system_proxy_on(self._store):
                    result = self.set_system_proxy(True)
                    if not result.get("ok"):
                        return result
            self._store.data["network_mode"] = mode
            self._store.save()
            return {"ok": True, "network_mode": mode}
        except Exception as exc:
            self._store.data["network_mode"] = previous_mode
            return {"ok": False, "error": str(exc)}

    def network_diagnostics(self) -> dict:
        route = _has_global_ipv6()
        connectivity = _test_ipv6_connectivity()
        dns_servers = _system_dns_servers()
        system_doh = _doh_template_count()
        config_doh, dot_templates = _configured_dns_protocols(getattr(self, "_profiles", None))
        doh_templates = system_doh + config_doh
        dns_ok = True
        ipv6_preferred = False
        try:
            addresses = socket.getaddrinfo("cp.cloudflare.com", 443, type=socket.SOCK_STREAM)
            dns_ok = bool(addresses)
            ipv6_preferred = bool(addresses) and addresses[0][0] == socket.AF_INET6
        except OSError:
            dns_ok = False
        proxy_on = is_system_proxy_on(self._store)
        dns_leak_suspected = bool(proxy_on and dns_servers and not any(
            server.startswith(("127.", "::1")) for server in dns_servers
        ))
        dns_resolver_ip = ""
        if dns_servers:
            dns_resolver_ip = _first_ip(_dns_query_txt("o-o.myaddr.l.google.com", dns_servers[0]))
        proxy_url = f"http://127.0.0.1:{int(self._store.data.get('mixed_port', 7890))}" if proxy_on else None
        proxy_egress_ip = _first_ip(_fetch_egress_ip(proxy_url)) if proxy_on else ""
        dns_leak_confirmed = bool(
            proxy_on and dns_resolver_ip and proxy_egress_ip and dns_resolver_ip != proxy_egress_ip
        )
        dns_encryption_conflict = bool((system_doh or config_doh) and dot_templates)
        lines = self.get_logs().get("lines", [])
        issues = _group_network_issues(lines)
        if route and not connectivity:
            _merge_network_issue(issues, "ipv6", 1, "IPv6 已有路由，但實際連線失敗")
        if not dns_ok:
            _merge_network_issue(issues, "dns", 1, "DNS 查詢失敗")
        if dns_leak_confirmed:
            _merge_network_issue(issues, "dns-leak", 1, "DNS 解析出口與代理出口不同，可能存在 DNS 洩漏")
        elif dns_leak_suspected:
            _merge_network_issue(issues, "dns-leak", 1, "系統代理開啟，但系統 DNS 不是本機位址")
        if ipv6_preferred and not connectivity:
            _merge_network_issue(issues, "ipv6-preference", 1, "DNS 優先回傳 IPv6，但 IPv6 無法連線")
        if dns_encryption_conflict:
            _merge_network_issue(issues, "dns-encrypted", 1, "同時偵測到 DoH 與 DoT 設定，可能造成解析衝突")
        return {
            "ok": True,
            "ipv6_route": route,
            "ipv6_connectivity": connectivity,
            "ipv6_preferred": ipv6_preferred,
            "dns_ok": dns_ok,
            "dns_servers": dns_servers,
            "system_doh_templates": system_doh,
            "config_doh_templates": config_doh,
            "doh_templates": doh_templates,
            "dot_templates": dot_templates,
            "dns_encryption_conflict": dns_encryption_conflict,
            "dns_leak_suspected": dns_leak_suspected,
            "dns_resolver_ip": dns_resolver_ip,
            "proxy_egress_ip": proxy_egress_ip,
            "dns_leak_confirmed": dns_leak_confirmed,
            "proxy_on": proxy_on,
            "network_mode": self._store.data.get("network_mode", "coexist"),
            "issues": issues,
        }

    def network_repair(self, action: str) -> dict:
        action = str(action or "").strip().lower()
        previous = None
        key = ""
        if action == "ipv6":
            key = "force_disable_ipv6"
            previous = self._store.data.get(key, False)
            self._store.data[key] = True
        elif action == "dns":
            key = "dns_mode"
            previous = self._store.data.get(key, "auto")
            self._store.data[key] = "backup"
        elif action == "dns-system":
            key = "dns_mode"
            previous = self._store.data.get(key, "auto")
            self._store.data[key] = "auto"
        elif action == "flush":
            try:
                subprocess.run(["ipconfig.exe", "/flushdns"], capture_output=True, text=True, timeout=12, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass
        else:
            return {"ok": False, "error": "無效的網路修復動作"}
        self._store.save()
        if action == "flush":
            return {"ok": True, "action": action}
        try:
            ok, message = self._core.reload_runtime()
            if not ok:
                if key:
                    self._store.data[key] = previous
                    self._store.save()
                return {"ok": False, "error": message}
            return {"ok": True, "action": action}
        except Exception as exc:
            if key:
                self._store.data[key] = previous
                try:
                    self._store.save()
                except Exception:
                    pass
            return {"ok": False, "error": str(exc)}

    def _any_proxy_on(self) -> bool:
        try:
            return int(get_system_proxy().get("enable", 0)) == 1
        except Exception:
            return False

    def _vpn_connected(self) -> bool:
        try:
            listing = self.vpn_list()
            return any(item.get("connected") for item in listing.get("connections") or [])
        except Exception:
            return False

    def detect_egress(self) -> dict:
        """Report the outbound path users actually see right now."""
        port = int(self._store.data.get("mixed_port", 7890))
        proxy_on = self._any_proxy_on()
        started = time.monotonic()
        attempts = [(("proxy", f"http://127.0.0.1:{port}") if proxy_on else ("direct", None))]
        if proxy_on:
            attempts.append(("direct", None))
        for kind, proxy_url in attempts:
            trace = _fetch_trace(proxy_url, timeout=8)
            if trace:
                ip, loc = trace
                via = "proxy" if kind == "proxy" else ("vpn" if self._vpn_connected() else "direct")
                return {
                    "ok": True,
                    "ip": ip,
                    "country": loc,
                    "via": via,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
        return {"ok": False, "error": "無法取得出口資訊", "via": "unknown"}

    def reconcile_network(self) -> dict:
        """Make the OS match the selected takeover mode."""
        mode = str(self._store.data.get("network_mode", "coexist"))
        changed = False
        needs_relogin = False
        error = ""
        if mode == "vpn" and self._any_proxy_on():
            result = self.set_system_proxy(False)
            changed = True
            if not result.get("ok"):
                error = str(result.get("error") or "")
            needs_relogin = self._any_proxy_on()
            if needs_relogin:
                error = "Windows 仍在保留系統代理設定，需要重新登入才會生效"
        elif mode == "proxy" and not is_system_proxy_on(self._store):
            result = self.set_system_proxy(True)
            changed = True
            if not result.get("ok"):
                error = str(result.get("error") or "")
        sys_proxy = self._any_proxy_on()
        return {
            "ok": not error,
            "mode": mode,
            "changed": changed,
            "needs_relogin": needs_relogin,
            "sys_proxy": sys_proxy,
            "proxy_matches_mode": not ((mode == "vpn" and sys_proxy) or (mode == "proxy" and not sys_proxy)),
            "error": error,
        }

    def reset_network(self) -> dict:
        """Give the machine back a clean network: undo only what KumoRoute changed."""
        warnings: list[str] = []
        disconnected: list[str] = []
        if platform.system().lower() == "windows":
            try:
                listing = self.vpn_list()
                for item in listing.get("connections") or []:
                    if not item.get("connected"):
                        continue
                    name = str(item.get("name") or "")
                    if not name:
                        continue
                    ok_disconnect, detail = _vpn_ras_disconnect(name)
                    if ok_disconnect:
                        disconnected.append(name)
                    else:
                        warnings.append(f"{name}：{detail}")
            except Exception as exc:
                warnings.append(f"讀取 VPN 連線失敗：{exc}")

        proxy_note = "未變更"
        proxy_restored = False
        if is_system_proxy_on(self._store):
            result = self.set_system_proxy(False)
            if result.get("ok"):
                proxy_note = "已還原為接管前的設定"
                proxy_restored = True
            else:
                warnings.append(str(result.get("error") or "系統代理還原失敗"))
                proxy_note = "還原失敗"
        elif self._store.data.get("original_proxy"):
            recovery = recover_stale_proxy(self._store) or {}
            if recovery.get("restored"):
                proxy_note = "已還原為接管前的設定"
                proxy_restored = True
            elif recovery.get("error"):
                warnings.append(str(recovery["error"]))
                proxy_note = "清理失敗"
            else:
                proxy_note = "已清除過期快照（目前代理非 KumoRoute 設定）"

        self._store.data["dns_mode"] = "auto"
        self._store.data["force_disable_ipv6"] = False
        self._store.data["vpn_proxy_pending"] = False
        self._store.data["network_mode"] = "coexist"
        try:
            self._store.save()
        except Exception as exc:
            warnings.append(f"保存設定失敗：{exc}")

        reloaded = False
        if self._core.is_up():
            try:
                reloaded, message = self._core.reload_runtime()
                if not reloaded:
                    warnings.append(f"核心重載失敗：{message}")
            except Exception as exc:
                warnings.append(f"核心重載失敗：{exc}")

        flushed = False
        try:
            if platform.system().lower() == "windows":
                flushed = subprocess.run(
                    ["ipconfig.exe", "/flushdns"],
                    capture_output=True, text=True, timeout=12, creationflags=CREATE_NO_WINDOW,
                ).returncode == 0
            elif platform.system().lower() == "darwin":
                flushed = subprocess.run(
                    ["dscacheutil", "-flushcache"], capture_output=True, text=True, timeout=12
                ).returncode == 0
            else:
                flushed = subprocess.run(
                    ["resolvectl", "flush-caches"], capture_output=True, text=True, timeout=12
                ).returncode == 0
        except Exception:
            flushed = False

        return {
            "ok": not warnings,
            "proxy": proxy_note,
            "proxy_restored": proxy_restored,
            "vpn_disconnected": disconnected,
            "dns_flushed": flushed,
            "core_reloaded": reloaded,
            "dns_mode": "auto",
            "ipv6_forced_off": False,
            "warnings": warnings,
        }

    def vpn_open_settings(self) -> dict:
        if platform.system().lower() != "windows":
            return {"ok": False, "error": "Windows VPN 僅支援 Windows"}
        try:
            os.startfile("ms-settings:network-vpn")
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": f"無法開啟 Windows VPN 設定：{exc}"}

    def record_ui_error(self, message: str, stack: str = "") -> dict:
        write_crash("ui", f"{message}\n{stack}")
        return {"ok": True}

    def _diagnostics_payload(self) -> tuple[str, dict]:
        running = self._core.is_up()
        sections = [
            "KumoRoute Diagnostics",
            f"generated_at: {_now()}",
            f"app_version: {APP_VERSION}",
            f"platform: {platform.platform()}",
            f"python: {sys.version.split()[0]}",
            f"core_running: {running}",
            f"core_version: {self._core.version() if running else '-'}",
            f"system_proxy: {is_system_proxy_on(self._store)}",
            f"mode: {self._store.data.get('mode', 'rule')}",
            f"mixed_port: {self._store.data.get('mixed_port')}",
            f"controller_port: {self._store.data.get('controller_port')}",
            f"profiles: {len(self._profiles.entries)}",
            f"active_profile_kind: {self._profiles.active_entry().get('kind', '')}",
        ]
        for label, source, limit in (
            ("APP LOG", data_dir() / "logs" / "app.log", 131072),
            ("CORE LOG", data_dir() / "logs" / "core.log", 131072),
            ("CRASH LOG", data_dir() / "logs" / "crash.log", 131072),
        ):
            try:
                raw = source.read_bytes()[-limit:].decode("utf-8", "replace")
            except OSError:
                raw = "(unavailable)"
            sections.append(f"\n===== {label} =====\n{raw}")
        return _sanitize_diagnostics_report("\n".join(sections))

    def diagnostics_preview(self) -> dict:
        try:
            text, summary = self._diagnostics_payload()
            return {"ok": True, "text": text, "summary": summary}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_diagnostics(self) -> dict:
        try:
            text, _ = self._diagnostics_payload()
            folder = Path.home() / "Downloads"
            if not folder.is_dir():
                folder = data_dir()
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"KumoRoute-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.txt"
            path.write_text(text, encoding="utf-8")
            return {"ok": True, "path": str(path)}
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
        try:
            parsed = urllib.parse.urlsplit((url or "").strip())
        except ValueError:
            return {"ok": False, "error": "無效的網址"}
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return {"ok": False, "error": "只允許不含帳密的 HTTP(S) 網址"}
        webbrowser.open(parsed.geturl())
        return {"ok": True}

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


try:
    try:
        from backup_support import install_api_methods
    except ModuleNotFoundError:
        _backup_spec = importlib.util.spec_from_file_location(
            "backup_support", Path(__file__).resolve().parent / "backup_support.py"
        )
        if not _backup_spec or not _backup_spec.loader:
            raise
        _backup_module = importlib.util.module_from_spec(_backup_spec)
        _backup_spec.loader.exec_module(_backup_module)
        install_api_methods = _backup_module.install_api_methods
    _app_module = sys.modules.get(__name__)
    if _app_module is None:
        _app_module = types.SimpleNamespace(**globals())
    install_api_methods(Api, _app_module)
except Exception as _backup_support_error:
    app_log(f'backup support unavailable: {_backup_support_error}')


def main() -> None:
    _ensure_std_streams()
    install_crash_hooks()
    if not acquire_single_instance():
        message_box("KumoRoute 已在執行中，請從系統托盤開啟。")
        return

    store = Store(data_dir() / "settings.json", DEFAULT_SETTINGS)
    proxy_recovery = recover_stale_proxy(store)
    profiles = Profiles(store)
    core = Core(store, profiles)
    api = Api(store, profiles, core)
    api._proxy_recovery = proxy_recovery
    if proxy_recovery:
        app_log(f"stale proxy recovery: {proxy_recovery}")

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
