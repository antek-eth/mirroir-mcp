#!/bin/bash
# Daily orchestrator: liveness check + scrape + rebuild + commit+push.
# Auto-launches Brave with --remote-debugging-port=9222 if not already running,
# using a separate user-data-dir to avoid disturbing the user's main profile.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

REPO="/Users/antekxxx/Coding/mirroir-mcp"
BRAVE_APP="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
BRAVE_PROFILE="/Users/antekxxx/.brave-scraper-profile"
DEBUG_PORT=9222

cd "$REPO"
mkdir -p logs
LOG="logs/$(date +%Y-%m-%d).log"
exec >> "$LOG" 2>&1
echo ""
echo "=== $(date) ==="

# 1) Ensure Brave with debug port is up (needed for Allegro).
if ! curl -sf "http://127.0.0.1:${DEBUG_PORT}/json/version" >/dev/null 2>&1; then
  echo "[brave] launching with debug port ${DEBUG_PORT}..."
  mkdir -p "$BRAVE_PROFILE"
  "$BRAVE_APP" \
    --remote-debugging-port="${DEBUG_PORT}" \
    --user-data-dir="$BRAVE_PROFILE" \
    --no-first-run --no-default-browser-check \
    --headless=new about:blank >/dev/null 2>&1 &
  sleep 4
fi

# 2) Pull latest
git pull --rebase --quiet || true

# 3) Liveness check
echo "[alive] starting..."
python3 scripts/check_alive.py

# 4) Scrape all saved searches
echo "[scrape] starting..."
python3 scripts/scrape_all.py

# 5) Rebuild HTML if DB changed
if ! git diff --quiet macbook_deals.json 2>/dev/null; then
  echo "[rebuild] HTML..."
  python3 pipeline.py rebuild
fi

# 6) Commit + push if anything changed
if ! git diff --quiet macbook_deals.json index.html 2>/dev/null; then
  git add macbook_deals.json index.html
  git commit -m "daily: $(date +%Y-%m-%d) auto-update listings"
  git push
  echo "[git] pushed."
else
  echo "[git] no changes."
fi

echo "=== done ==="
