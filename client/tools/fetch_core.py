"""Download the latest mihomo Windows amd64 (compatible) core and geodata into client/core/."""

import io
import json
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"
GEO_BASE = "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest"
GEO_FILES = {
    "geoip.metadb": f"{GEO_BASE}/geoip.metadb",
    "geosite.dat": f"{GEO_BASE}/geosite.dat",
}


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
    for name, url in GEO_FILES.items():
        dst = out / name
        if dst.exists():
            print("exists, skip", name)
            continue
        print("downloading", name)
        req = urllib.request.Request(url, headers={"User-Agent": "myclash-build"})
        with urllib.request.urlopen(req, timeout=900) as r:
            dst.write_bytes(r.read())
        print("saved", dst)


if __name__ == "__main__":
    main()
