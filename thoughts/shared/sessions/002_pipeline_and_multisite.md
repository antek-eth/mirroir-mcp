---
date: 2026-04-07T20:30:00+02:00
feature: Multi-site Deal Pipeline + Config-Grouped UI
status: in_progress
---

# Session Summary: Multi-site Deal Pipeline + Config-Grouped UI

## Objectives
- Build automation script (scrape → parse → benchmark → merge → HTML)
- Remove Geekbench AI, keep GB6 + LLM inference benchmarks
- Redesign UI to group by configuration with price ranges + listing links
- Scrape from multiple sources (pepper.pl, lantre.pl, olx.pl)

## Accomplishments

### Pipeline Script (pipeline.py)
- Built complete automation script with CLI: add, rebuild, clean, migrate, info
- Benchmark lookup tables: GB6 (15 chips) + LLM inference (15 chips)
- Spec parser: CPU, RAM, disk, screen, CPU/GPU cores from titles
- Date normalizer: Polish relative/absolute dates to ISO
- Deduplication by URL or unique field combo
- HTML generator with embedded data

### Config-Grouped UI (index.html)
- Complete redesign: cards grouped by chip + RAM + disk
- Price range per config (min - max)
- Expandable listings with individual links
- Cards view + Table view toggle
- "toks/1kPLN" value metric column
- "used" tag for secondhand listings
- Removed all Geekbench AI references
- Filters: chip, tier, RAM, disk, max price, search
- Sort: price, listings, GB6, Metal, Mem BW, LLM Q4, toks/1kPLN

### Multi-site Scraping
- pepper.pl: 145 deals migrated from old format
- lantre.pl: 72 deals scraped via dev-browser (product pages + listings)
- olx.pl: 13 deals scraped (MAX chips, marked as "used")
- After cleanup (removed 56 priceless): 178 deals total

### Data Cleanup
- Filled 177 missing CPU/GPU cores (inferred from chip model)
- Filled 11 missing RAM values
- Resolved 178 prices (including oldPrice fallback)
- Removed Geekbench AI fields from all entries
- Normalized all dates to ISO format
- Uploaded clean data to Google Sheets

### Google Sheets
- Database exported to: https://docs.google.com/spreadsheets/d/1TBDJdHA3c4LMEtYiprlPkxQ5xyHcy3n1WCCwocwvVAw/edit
- 21 clean columns, 178 rows, all numeric fields properly typed

## File Changes
```
pipeline.py                         - NEW: Automation script (benchmark tables, parser, HTML generator)
macbook_deals.json                  - NEW: Clean database (178 deals, multi-source)
index.html                         - MODIFIED: Config-grouped UI with price ranges
lantre_fresh.json                   - Scraped data (temp)
lantre_pro.json                     - Scraped data (temp)
lantre_raw.json                     - Scraped data (temp)
olx_max.json                        - Scraped data (temp)
olx_max2.json                       - Scraped data (temp)
```

## Discoveries
- dev-browser (`dev-browser` CLI) works great for scraping — runs sandboxed JS
- lantre.pl has product data in `data-name` and `data-price` attributes on cart buttons
- olx.pl uses `[data-cy="l-card"]` for listing cards with `h4` titles and `[data-testid="ad-price"]`
- dev-browser `writeFile()` writes to sandbox, not cwd — pipe stdout to capture output
- Playwright MCP browser can crash and can't be revived from Claude Code — use dev-browser CLI as alternative

## Scraping Patterns

### lantre.pl
```js
// Product listings
const buttons = document.querySelectorAll('button.tocart[data-name][data-price]');
// Dedup by SKU: btn.getAttribute('data-id')
// Price: btn.getAttribute('data-price')
// Title: btn.getAttribute('data-name')
```

### olx.pl
```js
// Listing cards
const cards = document.querySelectorAll('[data-cy="l-card"]');
// Title: card.querySelector('h4').textContent
// Price: card.querySelector('[data-testid="ad-price"]').textContent
// Link: card.querySelector('a[href*="/d/oferta/"]').href
```

## Open Questions / Next Steps
1. 18 deals still missing disk size (no title to parse from)
2. Could add more sites (allegro.pl, mediamarkt.pl, etc.)
3. Could add price history tracking (store date + price snapshots)
4. Spreadsheet could auto-sync via pipeline command

## To Resume
```bash
cd /Users/antekxxx/Coding/mirroir-mcp
# Add new listings:
dev-browser <<'EOF' > scraped.json
const page = await browser.getPage("site");
await page.goto("https://...");
// ... extraction JS
console.log(JSON.stringify(products));
EOF
python3 pipeline.py add scraped.json

# Rebuild HTML: python3 pipeline.py rebuild
# Show stats: python3 pipeline.py info
# Open UI: open index.html
```
