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
