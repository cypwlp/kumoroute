"""Bump or verify KumoRoute release versions consistently."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "client/app.py",
    "client/ui/app.js",
    "client/ui/index.html",
    "README.md",
    "packaging/README.txt",
    "site/index.html",
    "site/privacy.html",
    "site/terms.html",
    "tests/test_stats_export.py",
    "tests/test_update.py",
    "tauri/Cargo.toml",
    "tauri/tauri.conf.json",
    "tauri/src/state.rs",
    "tauri/src/commands.rs",
]
VERSION_RE = re.compile(r"0\.\d+\.\d+")


def current_version() -> str:
    text = (ROOT / "client/app.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text)
    if not match:
        raise SystemExit("找不到 APP_VERSION")
    return match.group(1)


def bump(new_version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", new_version):
        raise SystemExit("版本格式必須是 x.y.z")
    old_version = current_version()
    if tuple(map(int, new_version.split("."))) <= tuple(map(int, old_version.split("."))):
        raise SystemExit(f"新版本 {new_version} 必須大於目前版本 {old_version}")
    for name in FILES:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        updated = text.replace(old_version, new_version)
        if updated == text:
            raise SystemExit(f"{name} 找不到版本 {old_version}")
        path.write_text(updated, encoding="utf-8", newline="\n")
    lock = ROOT / "tauri/Cargo.lock"
    text = lock.read_text(encoding="utf-8")
    old_block = f'[[package]]\nname = "kumoroute"\nversion = "{old_version}"\n'
    new_block = f'[[package]]\nname = "kumoroute"\nversion = "{new_version}"\n'
    if old_block not in text:
        raise SystemExit("Cargo.lock 找不到 kumoroute package 版本")
    lock.write_text(text.replace(old_block, new_block, 1), encoding="utf-8", newline="\n")
    print(f"bumped {old_version} -> {new_version}")


def check() -> None:
    version = current_version()
    checks = {
        "tauri/Cargo.toml": f'version = "{version}"',
        "tauri/tauri.conf.json": f'"version": "{version}"',
        "tauri/src/state.rs": f'APP_VERSION: &str = "{version}"',
        "client/ui/index.html": f'id="app-version">v{version}',
        "site/index.html": f"v{version} · Windows / Linux / macOS",
    }
    for name, needle in checks.items():
        if needle not in (ROOT / name).read_text(encoding="utf-8"):
            raise SystemExit(f"{name} 版本不一致，預期 {version}")
    lock = (ROOT / "tauri/Cargo.lock").read_text(encoding="utf-8")
    if f'name = "kumoroute"\nversion = "{version}"' not in lock:
        raise SystemExit("Cargo.lock 的 kumoroute 版本不一致")
    print(f"version {version} consistent")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check or not args.version:
        check()
    else:
        bump(args.version)
        check()


if __name__ == "__main__":
    main()
