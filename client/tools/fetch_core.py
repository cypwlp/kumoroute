"""Download the latest mihomo Windows amd64 (compatible) core into client/core/."""

import io
import json
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"


def main():
    out = Path(__file__).resolve().parent.parent / "core"
    out.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(API, headers={"User-Agent": "myclash-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rel = json.load(r)
    wanted = f"mihomo-windows-amd64-compatible-{rel['tag_name']}.zip"
    asset = next((a for a in rel["assets"] if a["name"] == wanted), None)
    if not asset:
        raise SystemExit(f"asset not found: {wanted}")
    print("downloading", asset["name"], round(asset["size"] / 1048576, 1), "MB")
    with urllib.request.urlopen(asset["browser_download_url"], timeout=900) as r:
        data = r.read()
    z = zipfile.ZipFile(io.BytesIO(data))
    exe = next(n for n in z.namelist() if n.endswith(".exe"))
    (out / "mihomo.exe").write_bytes(z.read(exe))
    print("saved", out / "mihomo.exe")


if __name__ == "__main__":
    main()
