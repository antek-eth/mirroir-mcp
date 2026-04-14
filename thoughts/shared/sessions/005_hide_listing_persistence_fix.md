---
date: 2026-04-14
feature: Hidden-listing persistence across scraper refreshes
plan: (no plan doc — small bug fix)
research: (none)
status: complete
last_commit: 2712871
---

# Session Summary: Hidden listings reappearing after refresh

## Objectives
- Investigate why hidden listings in the frontend reappeared after each scraper refresh.
- Ship a fix that survives re-listings and is robust for typical Allegro/OLX URL churn.

## Accomplishments
- Root-caused the issue: `hiddenListings` in `localStorage` was keyed only by `url`. When a seller re-lists an item on Allegro/OLX, it gets a new URL, so the hide check no longer matches.
- Added a stable fingerprint per listing (`cpu|ram|disk|screen|title`, normalized) so hides survive URL changes.
- Updated the hide button, the filter, the button renderer, and added safe HTML-attr escaping for the `data-*` payload.
- Rebuilt `index.html` from `pipeline.py`'s template to include the fix.

## Discoveries
- `pipeline.py` contains the authoritative HTML template (`HTML_TEMPLATE`); `index.html` is a generated artifact. Any frontend change must be made in `pipeline.py` and then rebuilt via `python3 pipeline.py rebuild`.
- Dedup in `pipeline.py` (`make_dedup_key`) is URL-only for any deal with a URL. Since re-listings produce different URLs, those come in as new rows — same underlying issue the frontend now protects against.
- Today's refresh (2026-04-14) pulled 18 new listings; top value pick was Mac Mini M4 16/256 for 1599 PLN (≈15 tok/kPLN on llama2-7b q4 tg).

## Decisions Made
- **Client-side fix only.** Given the static GitHub Pages deployment, persistence is via `localStorage`. Cross-device sync would require an additional `hidden` field in `macbook_deals.json` plus a way to write back from the client — left as an optional follow-up.
- **Both keys stored, not migrated.** `hideListing(url, fp)` writes both to the same Set. Backward-compatible with existing URL-only entries.
- **Data-attr + dataset** instead of inline-escaped `onclick` argument — handles apostrophes in titles safely.

## File Changes
```
pipeline.py  | +18 / -4
index.html   | +15 / -4 (regenerated)
```
Commit: `2712871` — "Fix: hidden listings re-appear after scraper refresh"

## Test Status
- [x] `pipeline.py rebuild` completes cleanly (668 deals, 457KB).
- [x] Grep verification: `listingFp`, `htmlAttr`, `data-fp`, `this.dataset.fp`, `hideListing(this.dataset.*)` all present in generated HTML.
- [ ] Manual browser test (hide a listing → re-run scraper → verify it stays hidden) — not performed this session.

## Open Questions
- Do we want server-side persistence (hidden flag in `macbook_deals.json`) so hides sync across devices? Currently each device has its own `localStorage`.
- Scraper dedup (`pipeline.py` URL-keyed) still creates new DB rows for re-listings — not a correctness bug, but contributes to bloat over time.

## Unrelated Uncommitted Work (left as-is)
These were modified before this session and were **not** touched:
- `.gitignore` (modified)
- `scrapers/allegro.py` (modified)
- `scripts/daily.sh` (modified)
- `scripts/check_datadome.py` (untracked)
- `scripts/refresh_datadome.sh` (untracked)
- `.claude/` (untracked)

## Ready to Resume
```bash
cd /Users/antekxxx/Coding/mirroir-mcp
git log --oneline -5
# Optional manual verification:
python3 -m http.server 8000
# Open http://localhost:8000, hide a listing, run `bash scripts/daily.sh`,
# reload page and confirm it stays hidden.
```
