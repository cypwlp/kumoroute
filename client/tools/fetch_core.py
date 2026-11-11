"""Download mihomo core + geodata into client/core/ for the current platform."""

import gzip
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import unquote

LATEST_RELEASE = "https://github.com/MetaCubeX/mihomo/releases/latest"
RELEASE_DOWNLOAD = "https://github.com/MetaCubeX/mihomo/releases/download"
GEO_BASE = "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest"
GEO_FILES = {
    "geoip.metadb": f"{GEO_BASE}/geoip.metadb",
    "geosite.dat": f"{GEO_BASE}/geosite.dat",
}
DOWNLOAD_ATTEMPTS = 3


def download(url: str, timeout: int = 900) -> bytes:
    headers = {"User-Agent": "myclash-build"}
    last_error = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt == DOWNLOAD_ATTEMPTS:
                break
            delay = 2 ** (attempt - 1)
            print(
                f"download failed ({error}); retrying in {delay}s "
                f"[{attempt}/{DOWNLOAD_ATTEMPTS}]: {url}",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError(f"download failed after {DOWNLOAD_ATTEMPTS} attempts: {url}: {last_error}")


def latest_tag() -> str:
    """Resolve the latest tag without using GitHub's rate-limited API."""
    req = urllib.request.Request(
        LATEST_RELEASE,
        headers={"User-Agent": "myclash-build"},
        method="HEAD",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        final_url = response.geturl()
    marker = "/releases/tag/"
    if marker not in final_url:
        raise RuntimeError(f"cannot resolve latest mihomo tag from {final_url}")
    tag = unquote(final_url.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0])
    if not tag:
        raise RuntimeError(f"empty mihomo tag in {final_url}")
    return tag


def resolve_tag() -> str:
    pinned = os.environ.get("MIHOMO_VERSION", "").strip()
    return pinned or latest_tag()


def asset_url(tag: str, name: str) -> str:
    return f"{RELEASE_DOWNLOAD}/{tag}/{name}"


def fetch_core(tag: str, out: Path) -> None:
    if sys.platform.startswith("win"):
        data = download(asset_url(tag, f"mihomo-windows-amd64-compatible-{tag}.zip"))
        archive = zipfile.ZipFile(io.BytesIO(data))
        exe = next(name for name in archive.namelist() if name.endswith(".exe"))
        (out / "mihomo.exe").write_bytes(archive.read(exe))
        print("saved", out / "mihomo.exe")
    elif sys.platform.startswith("linux"):
        (out / "mihomo").write_bytes(
            gzip.decompress(download(asset_url(tag, f"mihomo-linux-amd64-compatible-{tag}.gz")))
        )
        (out / "mihomo").chmod(0o755)
        print("saved", out / "mihomo")
    elif sys.platform == "darwin":
        for arch, name in (("arm64", "mihomo-arm64"), ("amd64", "mihomo-x64")):
            (out / name).write_bytes(
                gzip.decompress(download(asset_url(tag, f"mihomo-darwin-{arch}-{tag}.gz")))
            )
            (out / name).chmod(0o755)
            print("saved", out / name)
    else:
        raise SystemExit(f"unsupported platform: {sys.platform}")


def main():
    out = Path(__file__).resolve().parent.parent / "core"
    out.mkdir(parents=True, exist_ok=True)
    tag = resolve_tag()
    print("mihomo", tag, "for", sys.platform)
    fetch_core(tag, out)
    for name, url in GEO_FILES.items():
        dst = out / name
        if dst.exists():
            print("exists, skip", name)
            continue
        dst.write_bytes(download(url))
        print("saved", dst)


if __name__ == "__main__":
    main()
