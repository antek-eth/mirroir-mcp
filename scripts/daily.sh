#!/bin/bash
# Daily orchestrator: browser freshness + cookie health + scrape + rebuild + commit+push.
# Launches Chrome (NON-headless) with --remote-debugging-port=9222 using a dedicated
# profile. Brave is never touched — we scope all kills to our scraper profile dir.
# Bypass for Allegro's DataDome shield uses a persisted `datadome` cookie at
# .datadome-cookie. When it expires, the cookie-health probe fails loudly and
# the scraper is not run (preventing silent 0-deal runs).
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

REPO="/Users/antekxxx/Coding/mirroir-mcp"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE="/Users/antekxxx/.chrome-scraper-profile"
DEBUG_PORT=9222
STATUS_FILE="$REPO/.daily-status"

cd "$REPO"
mkdir -p logs
LOG="logs/$(date +%Y-%m-%d).log"
exec >> "$LOG" 2>&1
echo ""
echo "=== $(date) ==="

write_status() {  # $1=state $2=message
  printf '{"state":"%s","at":"%s","msg":%s}\n' \
    "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$2")" \
    > "$STATUS_FILE"
}

# 1) Force-fresh Chrome scraper (kill ONLY our scraper profile, never Brave or user's Chrome)
echo "[chrome] recycling scraper instance..."
pkill -9 -f "user-data-dir=$CHROME_PROFILE" 2>/dev/null || true
sleep 1

# 2) Launch Chrome — NO --headless flag. Headless is detected & hard-blocked by DataDome.
echo "[chrome] launching on port ${DEBUG_PORT}..."
mkdir -p "$CHROME_PROFILE"
"$CHROME_APP" \
  --remote-debugging-port="${DEBUG_PORT}" \
  --user-data-dir="$CHROME_PROFILE" \
  --no-first-run --no-default-browser-check \
  --disable-blink-features=AutomationControlled \
  about:blank >/dev/null 2>&1 &
disown

# Wait up to 10s for CDP to accept connections
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://127.0.0.1:${DEBUG_PORT}/json/version" >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! curl -sf "http://127.0.0.1:${DEBUG_PORT}/json/version" >/dev/null 2>&1; then
  echo "[chrome] FAILED to open debug port"
  write_status error "chrome failed to open CDP debug port"
  exit 1
fi

# 3) Pull latest
git pull --rebase --quiet || true

# 4) DataDome cookie health check. If blocked, halt before running scrapers
# so we don't ship a silent 0-deal day.
echo "[datadome] checking cookie..."
if ! python3 scripts/check_datadome.py; then
  echo "[datadome] COOKIE EXPIRED — refresh with: ./scripts/refresh_datadome.sh"
  write_status cookie_expired "DataDome cookie expired — run ./scripts/refresh_datadome.sh"
  exit 1
fi

# 5) Liveness check (existing listings 404/removed detection)
echo "[alive] starting..."
python3 scripts/check_alive.py

# 6) Scrape all saved searches
echo "[scrape] starting..."
python3 scripts/scrape_all.py

# 5) Rebuild HTML if DB changed
if ! git diff --quiet macbook_deals.json 2>/dev/null; then
  echo "[rebuild] HTML..."
  python3 pipeline.py rebuild
fi

# 8) Commit + push if anything changed
if ! git diff --quiet macbook_deals.json index.html 2>/dev/null; then
  git add macbook_deals.json index.html
  git commit -m "daily: $(date +%Y-%m-%d) auto-update listings"
  git push
  echo "[git] pushed."
  write_status ok "daily run pushed changes"
else
  echo "[git] no changes."
  write_status ok "daily run completed, no new deals"
fi

echo "=== done ==="
