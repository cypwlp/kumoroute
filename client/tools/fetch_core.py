"""Download mihomo core + geodata into client/core/ for the current platform."""

import gzip
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"
GEO_BASE = "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest"
GEO_FILES = {
    "geoip.metadb": f"{GEO_BASE}/geoip.metadb",
    "geosite.dat": f"{GEO_BASE}/geosite.dat",
}


def download(url: str, timeout: int = 900) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "myclash-build"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def asset_url(rel: dict, name: str) -> str:
    asset = next((a for a in rel["assets"] if a["name"] == name), None)
    if not asset:
        raise SystemExit(f"asset not found: {name}")
    return asset["browser_download_url"]


def fetch_core(rel: dict, out: Path) -> None:
    tag = rel["tag_name"]
    if sys.platform.startswith("win"):
        data = download(asset_url(rel, f"mihomo-windows-amd64-compatible-{tag}.zip"))
        z = zipfile.ZipFile(io.BytesIO(data))
        exe = next(n for n in z.namelist() if n.endswith(".exe"))
        (out / "mihomo.exe").write_bytes(z.read(exe))
        print("saved", out / "mihomo.exe")
    elif sys.platform.startswith("linux"):
        (out / "mihomo").write_bytes(
            gzip.decompress(download(asset_url(rel, f"mihomo-linux-amd64-compatible-{tag}.gz")))
        )
        (out / "mihomo").chmod(0o755)
        print("saved", out / "mihomo")
    elif sys.platform == "darwin":
        for arch, name in (("arm64", "mihomo-arm64"), ("amd64", "mihomo-x64")):
            (out / name).write_bytes(
                gzip.decompress(download(asset_url(rel, f"mihomo-darwin-{arch}-{tag}.gz")))
            )
            (out / name).chmod(0o755)
            print("saved", out / name)
    else:
        raise SystemExit(f"unsupported platform: {sys.platform}")


def main():
    out = Path(__file__).resolve().parent.parent / "core"
    out.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(API, headers={"User-Agent": "myclash-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rel = json.load(r)
    print("mihomo", rel["tag_name"], "for", sys.platform)
    fetch_core(rel, out)
    for name, url in GEO_FILES.items():
        dst = out / name
        if dst.exists():
            print("exists, skip", name)
            continue
        dst.write_bytes(download(url))
        print("saved", dst)


if __name__ == "__main__":
    main()
