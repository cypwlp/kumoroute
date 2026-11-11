#!/usr/bin/env bash
# Sync site/ to the Tencent Cloud mirror (bare IP, HTTP only).
# Usage: bash packaging/deploy-tencent.sh
set -euo pipefail

HOST="${MYCLASH_MIRROR_HOST:-ubuntu@129.204.149.106}"
URL="${MYCLASH_MIRROR_URL:-http://129.204.149.106/}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ssh -o BatchMode=yes "$HOST" "echo ok" >/dev/null

tar -czf - -C "$ROOT/site" . | ssh -o BatchMode=yes "$HOST" \
  "rm -rf /tmp/myclash-site && mkdir -p /tmp/myclash-site && tar -xzf - -C /tmp/myclash-site && \
   sudo mkdir -p /var/www/myclash && sudo cp -a /tmp/myclash-site/. /var/www/myclash/ && \
   sudo chown -R root:root /var/www/myclash && rm -rf /tmp/myclash-site"

code=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
echo "deployed: $URL -> HTTP $code"
