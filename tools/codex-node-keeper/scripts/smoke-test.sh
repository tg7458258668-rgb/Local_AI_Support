#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOCKET="${MIHOMO_SOCKET:-/tmp/verge/verge-mihomo.sock}"

echo "1. Building app..."
"$ROOT_DIR/scripts/build.sh" >/tmp/codex-node-keeper-build.log
tail -2 /tmp/codex-node-keeper-build.log

echo "2. Checking Mihomo version..."
curl --unix-socket "$SOCKET" -sS --max-time 5 http://localhost/version
echo

echo "3. Reading OpenAI selector..."
curl --unix-socket "$SOCKET" -sS --max-time 5 http://localhost/proxies/OpenAI
echo

echo "4. Testing current API path through local mixed proxy..."
curl -I -sS --max-time 12 \
  --proxy http://127.0.0.1:7897 \
  -o /dev/null \
  -w 'code=%{http_code} total=%{time_total}\n' \
  https://api.openai.com/v1/models

echo "Smoke test complete. No selector switch or config reload was performed."
