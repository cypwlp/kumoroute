#!/usr/bin/env bash
# Sync site/ to the Tencent Cloud mirror (bare IP, HTTP only).
# Usage: bash packaging/deploy-tencent.sh
set -euo pipefail

HOST="${KUMOROUTE_MIRROR_HOST:-ubuntu@129.204.149.106}"
URL="${KUMOROUTE_MIRROR_URL:-http://129.204.149.106/}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ssh -o BatchMode=yes "$HOST" "echo ok" >/dev/null

tar -czf - -C "$ROOT/site" . | ssh -o BatchMode=yes "$HOST" \
  "rm -rf /tmp/kumoroute-site && mkdir -p /tmp/kumoroute-site && tar -xzf - -C /tmp/kumoroute-site && \
   sudo mkdir -p /var/www/kumoroute && sudo cp -a /tmp/kumoroute-site/. /var/www/kumoroute/ && \
   sudo chown -R root:root /var/www/kumoroute && rm -rf /tmp/kumoroute-site"

code=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
echo "deployed: $URL -> HTTP $code"
