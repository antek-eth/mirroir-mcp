#!/bin/bash
# Daily orchestrator: check alive → scrape → rebuild → commit → push.
# Scrapers use camoufox with a persistent profile at .camoufox-profile,
# pinned to a saved fingerprint at .camoufox-fingerprint.pkl.
# If Allegro's DataDome session lapses, scrapers/allegro.py exits 3 and we
# surface the state so the user can re-run scripts/probe_camoufox_persistent.py.
set -euo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

REPO="/Users/antekxxx/Coding/mirroir-mcp"
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

# 1) Camoufox profile + fingerprint must exist (CONFIRM-solved at least once)
if [ ! -d "$REPO/.camoufox-profile" ]; then
  echo "[setup] .camoufox-profile missing — run: python3 scripts/probe_camoufox_persistent.py"
  write_status setup_needed "camoufox profile missing — run scripts/probe_camoufox_persistent.py"
  exit 1
fi
python3 scripts/ensure_fingerprint.py

# 2) Pull latest (stash first so a dirty tree doesn't block us)
if ! git diff --quiet 2>/dev/null; then
  git stash push --include-untracked --quiet -m "daily-autostash" || true
  STASHED=1
else
  STASHED=0
fi
git pull --rebase --quiet || true
if [ "$STASHED" = "1" ]; then
  git stash pop --quiet || true
fi

# 3) Liveness check (existing listings 404/removed detection)
echo "[alive] starting..."
python3 scripts/check_alive.py

# 4) Scrape all saved searches
echo "[scrape] starting..."
set +e
python3 scripts/scrape_all.py
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  # scrape_all.py always returns 0; RC != 0 means a sub-scraper crashed out.
  echo "[scrape] exited with rc=$RC"
fi

# 5) Detect camoufox session loss by scanning the day's log for the scraper's
# self-report line. Allegro scraper exits 3 on BLOCKED.
if grep -q "BLOCKED — DataDome session lost" "$LOG" 2>/dev/null; then
  echo "[scrape] DataDome session lost"
  write_status camoufox_session_expired "Allegro DataDome session lapsed — run ./scripts/probe_camoufox_persistent.py"
  exit 1
fi

# 6) Rebuild HTML if DB changed
if ! git diff --quiet macbook_deals.json 2>/dev/null; then
  echo "[rebuild] HTML..."
  python3 pipeline.py rebuild
fi

# 7) Commit + push if anything changed
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
