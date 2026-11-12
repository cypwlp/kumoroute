"""Start the bundled mihomo core on a clean runner and verify its local API."""

import json
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def core_path() -> Path:
    if sys.platform.startswith("win"):
        return ROOT / "client" / "core" / "mihomo.exe"
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        name = "mihomo-arm64" if machine in ("arm64", "aarch64") else "mihomo-x64"
        return ROOT / "client" / "core" / name
    return ROOT / "client" / "core" / "mihomo"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def local_json(port: int, path: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
        return json.load(response)


def main() -> None:
    binary = core_path()
    if not binary.is_file():
        raise SystemExit(f"missing core binary: {binary}")

    controller = free_port()
    mixed = free_port()
    with tempfile.TemporaryDirectory(prefix="kumoroute-smoke-") as tmp:
        root = Path(tmp)
        config = root / "config.yaml"
        log = root / "core.log"
        config.write_text(
            "\n".join([
                f"mixed-port: {mixed}",
                "allow-lan: false",
                f"external-controller: 127.0.0.1:{controller}",
                "mode: rule",
                "log-level: warning",
                "proxies: []",
                "rules:",
                "  - MATCH,DIRECT",
                "",
            ]),
            encoding="utf-8",
        )
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x08000000
        with open(log, "wb") as output:
            proc = subprocess.Popen(
                [str(binary), "-d", str(root), "-f", str(config)],
                cwd=str(root),
                stdout=output,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
            try:
                version = None
                for _ in range(60):
                    if proc.poll() is not None:
                        break
                    try:
                        version = local_json(controller, "/version").get("version")
                        break
                    except Exception:
                        time.sleep(0.25)
                if not version:
                    raise SystemExit("mihomo core did not become ready\n" + log.read_text(encoding="utf-8", errors="replace"))
                connections = local_json(controller, "/connections")
                if connections.get("connections") is not None and not isinstance(connections.get("connections"), list):
                    raise SystemExit(f"unexpected connections response: {connections}")
                print(f"SMOKE OK platform={sys.platform} core={version}")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
