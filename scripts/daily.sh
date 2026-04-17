#!/bin/bash
# Daily orchestrator: scrape → alive → mark_stale → outliers → rebuild → commit → push.
#
# ORDERING INVARIANT: mark_stale.py --apply MUST run AFTER scrape_all.py in the
# same day. Otherwise the backfill values of `last_seen_in_search` (stale by
# definition) will trigger false-positive staleness expiry. Never invoke
# mark_stale.py --apply manually before today's scrape has completed.
#
# Anti-bot-sensitive steps use scrapers/scrappey_client.py as the canonical path:
#   - scrapers/allegro.py, scrapers/allegrolokalnie.py: Scrappey only (DataDome).
#   - scrapers/olx.py: camoufox primary when .camoufox-profile exists, Scrappey fallback.
#   - scripts/check_alive.py: HEAD only, no Scrappey — 404/410/451 early-expire.
#     Ambiguous statuses fall through to scripts/mark_stale.py.
#   - scripts/mark_stale.py: zero-network; uses today's scrape coverage as the
#     liveness signal. Listings absent from scrape >GRACE_DAYS get expired.
#   - scripts/check_outliers.py: Scrappey only — no local camoufox dependency.
# A missing / exhausted Scrappey key fails the run with an action-required summary.
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

# Reconcile hookpath so the pre-commit version bump never silently skips.
bash scripts/install-hooks.sh || echo "[hooks] install failed — continuing" >&2

write_status() {  # $1=state $2=message
  printf '{"state":"%s","at":"%s","msg":%s}\n' \
    "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$2")" \
    > "$STATUS_FILE"
}

db_size() {
  python3 -c 'import json,sys,pathlib; print(len(json.loads(pathlib.Path("macbook_deals.json").read_text())))' 2>/dev/null || echo 0
}

# Initialize fresh summary for this run
python3 scripts/summary.py reset daily "$LOG"
python3 scripts/summary.py count-before "$(db_size)"

# 1) Allegro uses Scrappey (API) — no browser profile needed.
#    OLX still uses camoufox when a profile exists and falls back to Scrappey.
if [ -d "$REPO/.camoufox-profile" ]; then
  python3 scripts/ensure_fingerprint.py
else
  echo "[setup] .camoufox-profile missing — OLX will use Scrappey fallback"
fi

# Scrappey key must be present for Allegro + OLX fallback.
if [ ! -s "$REPO/.scrappey-key" ] && [ -z "${SCRAPPEY_KEY:-}" ]; then
  echo "[setup] missing Scrappey key — put it in .scrappey-key or \$SCRAPPEY_KEY"
  write_status setup_needed "Scrappey key missing — create .scrappey-key"
  python3 scripts/summary.py action "Scrappey key missing — create .scrappey-key"
  python3 scripts/summary.py finalize setup_needed
  exit 1
fi

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

# 3) Scrape all saved searches FIRST — this bumps last_seen_in_search on every
#    URL that's still listed, feeding the search-based liveness signal for
#    step 5 (mark_stale.py).
echo "[scrape] starting..."
set +e
python3 scripts/scrape_all.py
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  # scrape_all.py always returns 0; RC != 0 means a sub-scraper crashed out.
  echo "[scrape] exited with rc=$RC"
fi

# 3a) Detect a scraper hard-block (Scrappey couldn't solve the upstream challenge).
# Allegro and OLX both exit 3 on BLOCKED; they log "BLOCKED — Scrappey failed".
if grep -q "BLOCKED — Scrappey failed" "$LOG" 2>/dev/null; then
  echo "[scrape] Scrappey failed — check .scrappey-key balance + service status"
  write_status scrappey_failed "Scrappey failed — check .scrappey-key balance / service status"
  python3 scripts/summary.py action "Scrappey failed — check .scrappey-key balance + service status"
  python3 scripts/summary.py count-after "$(db_size)"
  python3 scripts/summary.py finalize scrappey_failed
  exit 1
fi

# 4) Liveness check — HEAD early-confirm for hosts where HEAD gives a clear
#    status (404/410/451 → expired immediately, everything else is a no-op
#    because the search-based path in step 5 handles ambiguity).
echo "[alive] starting..."
python3 scripts/check_alive.py

# 5) Search-based staleness sweep — mark listings expired if they haven't
#    appeared in any scrape's results for the grace window. Un-expire any
#    previously staleness-expired listing that showed up again today. Respects
#    a safety gate: if any host's scrape returned 0 items, its deals are
#    skipped entirely so a broken scrape can't nuke the DB.
echo "[mark_stale] starting..."
python3 scripts/mark_stale.py --apply

# 6) Auto-outlier scan (flags broken/incomplete listings before they skew the view).
# Best-effort: a failure here must not block the daily run.
echo "[outliers] checking..."
python3 scripts/check_outliers.py || true

# 7) Rebuild HTML if DB changed
if ! git diff --quiet macbook_deals.json 2>/dev/null; then
  echo "[rebuild] HTML..."
  python3 pipeline.py rebuild
fi

# 8) Commit + push if anything changed (include .hidden-fps.json so auto-hides persist)
python3 scripts/summary.py count-after "$(db_size)"

if ! git diff --quiet macbook_deals.json index.html .hidden-fps.json 2>/dev/null || \
   git ls-files --others --exclude-standard --error-unmatch .hidden-fps.json >/dev/null 2>&1; then
  git add macbook_deals.json index.html .hidden-fps.json 2>/dev/null || true
  git commit -m "daily: $(date +%Y-%m-%d) auto-update listings"
  git push
  echo "[git] pushed."
  write_status ok "daily run pushed changes"
else
  echo "[git] no changes."
  write_status ok "daily run completed, no new deals"
fi

python3 scripts/summary.py finalize ok
echo "=== done ==="
