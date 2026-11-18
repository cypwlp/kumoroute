#!/usr/bin/env bash
# Hourly check on the Tencent VM: when GitHub publishes a newer release,
# refresh the local download mirror. Logs to /var/log/kumoroute-mirror.log.
set -uo pipefail
LOG=${HOME:-/home/ubuntu}/kumoroute-mirror.log
exec >>"$LOG" 2>&1
echo "[$(date -u +%FT%TZ)] check"

latest=$(curl -fsSL -m 20 -H 'Accept: application/vnd.github+json' \
  https://api.github.com/repos/cypwlp/kumoroute/releases/latest \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tag_name", ""))' 2>/dev/null)
[ -n "$latest" ] || { echo "cannot read latest tag from GitHub"; exit 1; }

local_tag=$(python3 -c \
  'import json; print(json.load(open("/var/www/kumoroute/downloads/release.json")).get("tag_name", ""))' \
  2>/dev/null || true)
if [ "$latest" = "$local_tag" ]; then
  echo "up to date: $latest"
  exit 0
fi

echo "new release: ${local_tag:-none} -> $latest"
rm -rf /tmp/kumoroute-assets /tmp/mirror-status.txt /tmp/mirror.log
bash /usr/local/bin/kumoroute-mirror-fetch.sh
status=$(tail -1 /tmp/mirror-status.txt 2>/dev/null || true)
echo "fetch status: $status"
[ "$status" = "DONE" ]
