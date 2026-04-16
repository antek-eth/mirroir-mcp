#!/bin/bash
# Removes the daily scraper + control server LaunchAgents.
set -euo pipefail
for label in com.mirroir.daily com.mirroir.server; do
  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
  echo "removed $label"
done
