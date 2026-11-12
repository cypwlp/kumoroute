"""Assemble KumoRoute release folder and zip from build artifacts."""

import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "tauri" / "target" / "release" / "kumoroute.exe"
CORE_DIR = ROOT / "client" / "core"
README = ROOT / "packaging" / "README.txt"
OUT_DIR = ROOT / "dist"
STAGE = OUT_DIR / "rust" / "KumoRoute"
ZIP_PATH = OUT_DIR / "KumoRoute-win-x64.zip"
CORE_FILES = ("mihomo.exe", "geoip.metadb", "geosite.dat", "LICENSE-GPL3.txt")
LEGAL_FILES = ("LICENSE", "NOTICE.md", "PRIVACY.md", "TERMS.md")


def main():
    if not EXE.is_file():
        sys.exit(f"missing exe: {EXE} (run cargo build --release first)")
    for name in CORE_FILES:
        if not (CORE_DIR / name).is_file():
            sys.exit(f"missing core file: {CORE_DIR / name} (run client/tools/fetch_core.py)")
    for name in LEGAL_FILES:
        if not (ROOT / name).is_file():
            sys.exit(f"missing legal file: {ROOT / name}")
    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "core").mkdir(parents=True)
    shutil.copy2(EXE, STAGE / "KumoRoute.exe")
    shutil.copy2(README, STAGE / "README.txt")
    for name in LEGAL_FILES:
        shutil.copy2(ROOT / name, STAGE / name)
    for name in CORE_FILES:
        shutil.copy2(CORE_DIR / name, STAGE / "core" / name)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(STAGE):
            for f in files:
                p = Path(root) / f
                z.write(p, Path("KumoRoute") / p.relative_to(STAGE))
    digest = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    (OUT_DIR / "SHA256SUMS.txt").write_text(
        f"{digest}  KumoRoute-win-x64.zip\n", encoding="utf-8"
    )
    print("zip:", ZIP_PATH, round(ZIP_PATH.stat().st_size / 1048576, 1), "MB")
    print("sha256:", digest)


if __name__ == "__main__":
    main()
