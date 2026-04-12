---
date: 2026-04-12
topic: Web scraping and parsing techniques for MacBook deals explorer
type: reference
---

# Scraping & Parsing Reference Guide

## Current Data Sources

### 1. **OLX.pl** ✅ Working
- **Tool**: `scrapers/olx.py`
- **Method**: `dev-browser` with JavaScript evaluation
- **Selectors**: 
  - Cards: `[data-cy="l-card"]`
  - Title: `h4` within card
  - Price: `[data-testid="ad-price"]`
  - Link: `a[href*="/d/oferta/"]`
- **Rate Limits**: No known limits, fast scraping
- **Notes**: 
  - Works well after Brave restart
  - Timeout ~40 seconds per page
  - Returns JSON array with title, price, url, source

**Usage**:
```bash
python3 scrapers/olx.py "URL" --pages 1
```

### 2. **Allegro.pl** ❌ Blocked
- **Status**: 403 Forbidden via HTTP
- **Issue**: Requires JavaScript rendering, blocks automated requests
- **Alternative**: Manual URL collection from browser
- **Note**: Can't be scraped without Brave browser

### 3. **Vinted.pl** ⚠️ Limited
- **Status**: Some listings appear in OLX results
- **Method**: Would need custom scraper
- **Note**: Fewer MacBook listings than OLX/Allegro

### 4. **Lantre.pl** ⚠️ Untested
- **Tool**: `scrapers/lantre.py` exists but needs testing
- **Status**: 1 listing currently in database

---

## Parsing Pipeline

### Entry Point: `pipeline.py add <file.json>`

**Flow**:
1. Read raw JSON from scraper output
2. Call `process_raw_listings(raw, source)` 
3. For each listing:
   - Parse specs from title: `parse_specs(title, description)`
   - Extract CPU, RAM, Disk, Screen, Model
   - Assign benchmarks from lookup tables
   - Normalize date
   - Build deal entry

### Key Parsing Functions

#### `parse_cpu(text)` → "M4 MAX"
- **Pattern**: `M(\d)\s*(MAX|PRO|ULTRA)?`
- **Examples**: "M4 MAX", "M3 PRO", "M1"
- **Note**: Case-insensitive, handles spaces

#### `parse_ram(text)` → "24GB"
- **Patterns** (in order):
  1. "(\d+)\s*GB\s*(?:RAM|UNIFIED|PAMIĘCI)"
  2. Bare RAM values: `\b(8|16|18|24|32|36|48|64|96|128|192)\s*GB\b`
  3. After chip: "M\d\s*(?:MAX|PRO|ULTRA)?\s+(\d{1,3})" (if valid RAM size)
- **Note**: Max valid is 192GB (filters parse errors)

#### `parse_disk(text)` → "1TB" or "512GB"
- **Patterns** (in order):
  1. TB first: `(\d+)\s*TB`
  2. Large GB values labeled as SSD: `(\d{3,4})\s*GB\s*(?:SSD|DYSK|NVME)`
  3. Any 3-4 digit GB value (>=256 is always disk for Macs)
  4. Fallback: "256" or "512" without unit
- **Logic**: >=256GB is disk (RAM maxes at 192GB for Macs)

#### `parse_screen(text)` → "13", "14", "16", or "Studio"/"Mini"
- **Patterns**:
  1. With quote: `(\d{2})[,.]?\d*\s*["\u201c...]` → validate in [13,14,16]
  2. After model name: `(?:pro|macbook|book)\s+(\d{2})\b`
  3. With unit: `(\d{2})\s*[-]?\s*(?:cal|inch)`
- **Special**: "Studio" or "Mini" set as screen value (not size)

#### `parse_specs(title, description)` → All specs + model
- **Model Logic**:
  - If "studio" in title → "Studio"
  - If "mini" in title → "Mini"  
  - Otherwise: Check for "air" → "Air" or "Pro"
  - Returns: "Air", "Pro", "Studio", "Mini" (simplified categories)

---

## Deduplication

**Key**: `make_dedup_key(deal)`
- Primary: URL (if available)
- Fallback: `model|cpu|ram|disk|price|oldPrice|date|temperature`

**Process**: `merge_deals(existing, new_deals)`
- Track seen URLs
- Skip if already in database
- Count: added vs duplicates

---

## Database Structure

**File**: `macbook_deals.json`

**Fields per entry**:
```json
{
  "title": "string",
  "model": "Air|Pro|Studio|Mini",
  "cpu": "M1|M2|M3|M4|M1 MAX|M1 PRO|M1 ULTRA|...",
  "ram": "8GB|16GB|24GB|32GB|...",
  "disk": "256GB|512GB|1TB|2TB",
  "screen": "13|14|16|Studio|Mini",
  "cpuCores": "8-core",
  "gpuCores": "10-core",
  "price": "4999 zł",
  "priceNum": 4999.0,
  "url": "https://...",
  "source": "olx.pl|allegro.pl|vinted.pl|lantre.pl",
  "used": false,
  "broken": false,
  "date": "2026-04-12",
  "gb6_single": 3793,
  "gb6_multi": 14921,
  "llm_q4": 24.11,
  "toksPerKPLN": 5.2
}
```

---

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Dev-browser timeout | Restart Brave with `--remote-debugging-port=9222` |
| No CPU found (SKIP) | Entry is old Intel Mac or missing chip identifier |
| Duplicate skipped | URL already in database from previous scrape |
| JSON parse error | Mixed stdout/stderr in scraper output - filter valid JSON lines |
| Allegro 403 forbidden | HTTP blocked, need browser or manual URL collection |

---

## Quick Commands

```bash
# Add listings from scraper output
python3 pipeline.py add olx_results.json

# Rebuild HTML (regenerate explorer from DB)
python3 pipeline.py rebuild

# Show database stats
python3 pipeline.py info

# Check database integrity
python3 pipeline.py clean

# Scrape OLX page 1
python3 scrapers/olx.py "URL" --pages 1

# Commit changes
git add macbook_deals.json index.html
git commit -m "Add [X] new listings from [source]"
```

---

## Benchmark Tables

Embedded in `pipeline.py`:

### **GB6** (Geekbench 6)
- Single-core, multi-core, metal GPU scores
- Keys: "gb6_single", "gb6_multi", "gb6_metal"

### **LLM** (Llama 2 7B inference)
- Memory bandwidth, GPU cores, various precision toks/sec
- Keys: "mem_bw_gbs", "llama2_7b_q4_tg", etc.
- Used to calculate "toksPerKPLN" metric

---

## Next Steps for Automation

1. **Allegro**: Needs browser-based collection or API access
2. **Vinted**: Custom scraper using similar OLX approach
3. **Scheduling**: Use cron/CronCreate for daily scrapes
4. **Alerts**: Flag notable deals (high specs, low price)
