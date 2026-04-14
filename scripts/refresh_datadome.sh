#!/bin/bash
# Interactive helper: refresh the DataDome session cookie used by the Allegro scraper.
#
# Why this exists: DataDome blocks fresh scraper profiles. We sidestep it by injecting
# a `datadome` cookie that was granted to a real human-driven browser. This script
# walks you through copying the cookie from your normal Brave into .datadome-cookie,
# then validates that it actually works against Allegro.
#
# Prerequisites:
#   - Your normal Brave (or any browser) is logged into / has visited allegro.pl
#   - The scraper Chrome is running on port 9222 (daily.sh handles that, or run it
#     manually the same way)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
COOKIE_FILE="$REPO/.datadome-cookie"

cat <<'INSTRUCTIONS'
=== DataDome cookie refresh ===

1) In your normal Brave (NOT the scraper Chrome), open:
   https://allegro.pl/kategoria/laptopy-491?string=macbook
   Make sure you see real listings (no "You have been blocked" page).

2) Open DevTools (Cmd+Option+I), go to: Application → Cookies → https://allegro.pl

3) Find the cookie named  datadome  and copy its VALUE (long string, starts with
   a letter/digit, ~100–200 chars).

INSTRUCTIONS

printf 'Paste the datadome cookie value and press Enter:\n> '
read -r NEW_VALUE

# Basic sanity
if [ -z "${NEW_VALUE// }" ]; then
  echo "empty value, aborting" >&2
  exit 1
fi
if [ ${#NEW_VALUE} -lt 40 ]; then
  echo "value is too short (${#NEW_VALUE} chars), aborting" >&2
  exit 1
fi

printf '%s\n' "$NEW_VALUE" > "$COOKIE_FILE"
chmod 600 "$COOKIE_FILE"
echo "[datadome] wrote new cookie (${#NEW_VALUE} chars) to $COOKIE_FILE"

# Validate
echo "[datadome] probing Allegro to confirm the cookie works..."
if python3 "$REPO/scripts/check_datadome.py"; then
  echo "[datadome] ✓ cookie refreshed and verified"
  exit 0
else
  echo "[datadome] ✗ probe failed — the cookie didn't unblock Allegro."
  echo "            Possible causes: copy-paste added whitespace, cookie was already expired in Brave,"
  echo "            or IP reputation has decayed and even a fresh cookie won't pass."
  exit 1
fi
