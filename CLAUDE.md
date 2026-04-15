# MacBook Deal Explorer

## Data Quality Notes

### Outliers in tok/s (toksPerKPLN)
If you see an outlier config with unusually high or low tok/s per 1000 PLN, **verify the listing manually**. Usually there's something wrong with the data:

**Example of bad data:**
- https://allegrolokalnie.pl/oferta/macbook-pro-a3185-m4-max-2024-bez-matrycystan-nieznany
  - Listed as: MacBook Pro M4 Max
  - Reality: Just the **bottom chassis without screen**, non-working
  - Impact: Skews price-to-performance metrics

**Pattern to watch:**
- Extremely low prices for high-end specs → likely broken, damaged, or incomplete
- Missing key info in listing → red flag for quality control

When found, either:
1. Remove the listing from `macbook_deals.json` (bad data)
2. Add `"broken": true` field to skip it in analysis
3. Manually correct the price if it's a simple data entry error

---

## Workflows

### Add listings from scraper
```bash
python3 scrapers/allegro.py "<URL>" --pages 1 | python3 pipeline.py add /dev/stdin
```

### Rebuild HTML
```bash
python3 pipeline.py rebuild
```

### Clean & verify database
```bash
python3 pipeline.py clean
```

## URLs & References

- **Allegro desktop**: https://allegro.pl/kategoria/laptopy-491 (use /dev-browser)
- **OLX**: Works with standard scraper
- **Database**: `macbook_deals.json` (JSON array)
- **Explorer**: Served at http://localhost:8000 or GitHub Pages

## Tools

- Scraper: `scrapers/allegro.py`, `scrapers/olx.py`
- Pipeline: `pipeline.py` (parse, dedupe, generate HTML)
- Frontend: Single-file `index.html` with embedded JS

---

## Design Context

### Users
Solo personal tool — built by and for one person hunting MacBook deals on Polish marketplaces (Allegro, OLX, Pepper.pl). The user is technically fluent, comfortable with dense data, and values efficiency over hand-holding. There is no onboarding concern; the tool should trust the user completely.

### Brand Personality
**Terminal. Precise. Uncompromising.**

Personal instrument, not a product. Should feel like a well-crafted CLI rendered as a webpage — authoritative, data-forward, with zero decoration that doesn't carry information. Emotional goal: quiet confidence — *the data is here, it's trustworthy, and it helps me find the best deal fast.*

### Aesthetic Direction
- **Dark mode only** — near-black backgrounds (`#0a0a0c` family), never light
- **Green accent** (`#4ade80`) as the single hero color; all other colors are semantic (chip gen badges, deal heat indicators)
- **Monospace-first** — JetBrains Mono for all data, labels, prices, metadata; DM Sans only for prose-length strings
- **Dense, not claustrophobic** — information-rich layouts are correct; breathing room from deliberate spacing, not large empty zones
- **Anti-reference**: No e-commerce styling — no product photography, no "Add to cart" UI, no Allegro/OLX visual bleed-through

### Design Principles
1. **Data is the UI.** Every pixel serves information. Decoration exists only when it encodes meaning.
2. **Surface everything without clicking.** Benchmarks, specs, price ranges, and source quality visible at a glance by default.
3. **Trust the user.** No explanatory tooltips, no confirmation dialogs, no progressive disclosure that hides useful data.
4. **Terminal aesthetics, not terminal limitations.** Visual language from CLI tools — compact, monospace, low-contrast — but remains navigable and responsive.
5. **Anomalies deserve visual weight.** Broken listings, outlier prices, expired entries should be clearly flagged — not hidden, not alarming.
