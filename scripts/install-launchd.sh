#!/bin/bash
# Installs the daily scraper + local control server as user LaunchAgents.
# Idempotent: re-run to pick up plist changes.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA" "$REPO/logs"

for label in com.mirroir.daily com.mirroir.server; do
  src="$REPO/launchd/$label.plist"
  dst="$LA/$label.plist"
  if [ ! -f "$src" ]; then
    echo "missing: $src" >&2
    exit 1
  fi
  cp "$src" "$dst"
  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID" "$dst"
  launchctl enable "gui/$UID/$label" 2>/dev/null || true
  echo "installed $label"
done

echo ""
echo "daily scraper  → runs at 09:30 local every day"
echo "control server → http://127.0.0.1:8000 (keep-alive)"
echo ""
echo "check status with: launchctl print gui/\$UID/com.mirroir.server | head"
