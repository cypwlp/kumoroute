#!/usr/bin/env bash
# Runs on the Tencent VM (uploaded by packaging/sync_mirror.sh). Downloads release assets through a China-friendly
# GitHub proxy but verifies every byte against GitHub's own SHA256SUMS.txt.
set -uo pipefail
DIR=/tmp/kumoroute-assets
STATUS=/tmp/mirror-status.txt
BASE=https://github.com/cypwlp/kumoroute/releases/latest/download
PROXY=https://ghfast.top/
NAMES=(
  KumoRoute-win-x64-setup.exe
  KumoRoute-win-x64.zip
  KumoRoute-linux-x86_64.AppImage
  KumoRoute-linux-amd64.deb
  KumoRoute-macos-universal.dmg
)
mkdir -p "$DIR"
echo START > "$STATUS"

# Prefer the checksum file pushed over SSH by sync_mirror.sh (trusted hop);
# fall back to fetching it here when running unattended from cron.
if [ -s /tmp/kumoroute-sums.txt ]; then
  cp /tmp/kumoroute-sums.txt "$DIR/github-sums.txt"
  echo "sums: pushed over ssh"
else
  curl -fsSL --retry 5 --connect-timeout 15 -m 60 "$BASE/SHA256SUMS.txt" -o "$DIR/github-sums.txt" \
    || { echo FAIL_SUMS > "$STATUS"; exit 1; }
  echo "sums: fetched on vm"
fi

for name in "${NAMES[@]}"; do
  for attempt in 1 2 3; do
    curl -fsSL -C - --retry 3 --connect-timeout 15 --max-time 900 \
      "${PROXY}${BASE}/${name}" -o "$DIR/$name" && break
  done
  echo "$name $(stat -c%s "$DIR/$name" 2>/dev/null || echo 0)" >> "$STATUS"
done

cd "$DIR" || exit 1
if ! sha256sum -c github-sums.txt --ignore-missing; then
  echo FAIL_VERIFY > "$STATUS"; exit 1
fi

curl -fsSL --retry 5 --connect-timeout 15 \
  https://api.github.com/repos/cypwlp/kumoroute/releases/latest -o "$DIR/github-release.json" || true
python3 - "$DIR" <<'PY'
import datetime, json, pathlib, sys
folder = pathlib.Path(sys.argv[1])
base = "http://129.204.149.106/downloads/"
try:
    rel = json.loads((folder / "github-release.json").read_text(encoding="utf-8"))
    tag, notes = rel.get("tag_name", ""), str(rel.get("body") or "")[:4000]
    published, html_url = str(rel.get("published_at") or ""), str(rel.get("html_url") or "")
except Exception:
    tag, notes, published = "", "", ""
    html_url = "https://github.com/cypwlp/kumoroute/releases/latest"
assets = []
for p in sorted(folder.glob("KumoRoute-*")):
    assets.append({"name": p.name, "browser_download_url": base + p.name, "size": p.stat().st_size})
sums = folder / "SHA256SUMS.txt"
sums.write_text((folder / "github-sums.txt").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
assets.append({"name": "SHA256SUMS.txt", "browser_download_url": base + "SHA256SUMS.txt", "size": sums.stat().st_size})
manifest = {
    "tag_name": tag, "html_url": html_url, "published_at": published, "body": notes,
    "assets": assets,
    "_mirror": "Tencent Cloud fallback (HTTP; verified against GitHub SHA256SUMS.txt)",
    "_generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
(folder / "release.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("tag:", tag, "assets:", len(assets))
PY

sudo mkdir -p /var/www/kumoroute/downloads
sudo cp -f "$DIR"/KumoRoute-* "$DIR"/SHA256SUMS.txt "$DIR"/release.json /var/www/kumoroute/downloads/
sudo chmod 644 /var/www/kumoroute/downloads/*
echo DONE > "$STATUS"
