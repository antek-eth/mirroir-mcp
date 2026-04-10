---
date: 2026-04-10T14:50:00+02:00
feature: Multi-site Deal Pipeline + Config-Grouped UI
status: in_progress
---

# Session Summary: Scraper Scripts + Allegro Used Listings

## Objectives
- Resume pipeline work from session 002
- Scrape used MacBook MAX + PRO listings from Allegro.pl
- Create reusable scraper scripts for all sources
- Fix parser bugs found with Allegro title formats

## Accomplishments

### Parser Fixes (pipeline.py)
- `parse_screen`: handles European comma-decimal format (`16,2"` → `16`)
- `parse_disk`: requires 3+ digit GB values (prevents `32 GB SSD` → `32GB`), handles `/ 1024 GB` format
- `parse_ram`: catches bare numbers after chip model (`M1 MAX 64 1TB` → `64GB`)
- Re-parsed 10 Allegro entries fixing wrong screen/disk/RAM values

### Scraper Scripts (scrapers/)
Rewrote all three as Python scripts with proper architecture:
- `scrapers/olx.py` — OLX.pl: paginated via `?page=N`, title cleaning, price normalization
- `scrapers/allegro.py` — Allegro.pl: paginated via `?p=N`, CPU extraction from URL slug, URL dedup
- `scrapers/lantre.py` — Lantre.pl: paginated via `?p=N`, SKU dedup, product URL extraction

Key design: Python calls `dev-browser` once per page via `subprocess.run(input=js)` to avoid 30s script timeout. Compact JSON output minimizes LLM tokens.

### Data Added
- 20 used MacBook MAX listings from allegro.pl
- 51 used MacBook PRO listings from allegro.pl (16 needed CPU injection from URL slug)
- 1 bad entry removed (non-M CPU misidentified)
- Database: 178 → 315 deals (also includes MAX/PRO from session continuation)

## Discoveries
- Allegro titles often say "Apple M" without Pro/Max tier — URL slug contains it (e.g. `-m1-pro-`)
- dev-browser has 30s script timeout — multi-page while loops fail, must call once per page
- `<<EOF` heredoc in shell expands `$` — unsafe for JS injection, Python subprocess is better
- Allegro pagination `?p=N` returns same results when out of pages (no error), need URL-based dedup
- Allegro search includes Allegro Lokalnie results automatically

## File Changes
```
pipeline.py                              - MODIFIED: parse_screen, parse_disk, parse_ram fixes
scrapers/olx.py                          - NEW: Python scraper (replaced olx.sh)
scrapers/allegro.py                      - NEW: Python scraper (replaced allegro.sh)
scrapers/lantre.py                       - NEW: Python scraper (replaced lantre.sh)
macbook_deals.json                       - MODIFIED: 315 deals (was 245)
index.html                               - MODIFIED: rebuilt (315 deals, 215KB)
allegro_max_used.json                    - Scraped data (temp)
allegro_pro_used.json                    - Scraped data (temp)
allegro_pro_skipped_fix.json             - Scraped data (temp)
```

## Database Stats (315 deals)
```
By chip: M1 MAX 57, M1 PRO 31, M2 MAX 27, M2 PRO 11, M3 MAX 9, M3 PRO 21,
         M4 MAX 13, M4 PRO 19, M5 MAX 24, M5 PRO 19, M5 54, M4 19, M3 7, etc.
By source: pepper/lantre/olx 245 (prev), allegro.pl 70 (new)
```

## Scraping Patterns

### Usage (all scripts)
```bash
# Start Brave with remote debugging
/Applications/Brave\ Browser.app/Contents/MacOS/Brave\ Browser --remote-debugging-port=9222

# Scrape
./scrapers/allegro.py "<search-url>" --used --pages 3 > out.json
./scrapers/olx.py "<search-url>" --used > out.json
./scrapers/lantre.py "<category-url>" > out.json

# Add to database
python3 pipeline.py add out.json
```

## Open Questions / Next Steps
1. 177 deals still have source="?" (migrated from old pepper.pl format)
2. Lantre scraper untested live (no live test this session)
3. Could add pepper.pl scraper script
4. Could add price history tracking
5. Temp JSON files (allegro_*.json, olx_*.json, lantre_*.json) should be gitignored or cleaned

## To Resume
```bash
cd /Users/antekxxx/Coding/mirroir-mcp
python3 pipeline.py info
open index.html
# Scrape new listings:
./scrapers/allegro.py "<url>" --used > out.json && python3 pipeline.py add out.json
```
