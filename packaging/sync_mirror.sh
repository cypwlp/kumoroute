#!/usr/bin/env bash
# Sync the download site and the latest release artifacts to the Tencent VM.
# GitHub Pages / GitHub Releases stay primary; this is the mainland fallback.
#
# Usage: bash packaging/sync_mirror.sh
# Requires: SSH key for ubuntu@129.204.149.106 (override with KUMOROUTE_MIRROR_HOST).
set -euo pipefail

HOST="${KUMOROUTE_MIRROR_HOST:-ubuntu@129.204.149.106}"
URL="${KUMOROUTE_MIRROR_URL:-http://kumoroute.cypilu.cloud/}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30)
ssh() { command ssh "${SSH_OPTS[@]}" "$HOST" "$@"; }

ssh "echo ok" >/dev/null

# 1) Site content (identical to GitHub Pages).
tar -czf - -C "$ROOT/site" . | command ssh "${SSH_OPTS[@]}" "$HOST" \
  "rm -rf /tmp/kumoroute-site && mkdir -p /tmp/kumoroute-site && tar -xzf - -C /tmp/kumoroute-site && \
   sudo mkdir -p /var/www/kumoroute && sudo cp -a /tmp/kumoroute-site/. /var/www/kumoroute/ && \
   sudo chown -R root:root /var/www/kumoroute && rm -rf /tmp/kumoroute-site"
echo "site synced"

# 2) Upload the fetcher, run it in the background, then wait for completion.
#    The VM downloads through a proxy but verifies against GitHub checksums.
ssh 'rm -rf /tmp/kumoroute-assets /tmp/mirror-status.txt /tmp/mirror.log' || true
ssh 'cat > /tmp/mirror.sh' < "$ROOT/packaging/mirror_fetch.sh"
ssh 'nohup bash /tmp/mirror.sh > /tmp/mirror.log 2>&1 < /dev/null & echo started' >/dev/null

for _ in $(seq 1 90); do
  status=$(ssh 'cat /tmp/mirror-status.txt 2>/dev/null | tail -1' || true)
  case "$status" in
    DONE) break ;;
    FAIL_*) echo "mirror fetch failed: $status" >&2; ssh 'tail -20 /tmp/mirror.log' >&2; exit 1 ;;
  esac
  sleep 10
done
if [ "${status:-}" != "DONE" ]; then
  echo "mirror fetch timed out (last: ${status:-unknown})" >&2
  exit 1
fi
echo "release artifacts synced"

for path in downloads/release.json downloads/SHA256SUMS.txt downloads/KumoRoute-win-x64-setup.exe; do
  code=""
  for _ in 1 2 3 4 5; do
    code=$(curl -s -m 20 -o /dev/null -w '%{http_code}' "$URL$path")
    [ "$code" = "200" ] && break
    sleep 3
  done
  [ "$code" = "200" ] || { echo "mirror check failed: $path -> $code" >&2; exit 1; }
done
echo "mirror ready: ${URL}downloads/release.json"
