---
date: 2026-04-07T18:30:00+02:00
feature: MacBook Pro Deals Scraper + Benchmark Explorer
status: in_progress
---

# Session Summary: MacBook Pro Deals Scraper + Benchmark Explorer

## Objectives
- Scrape MacBook Pro deals from pepper.pl (all pages, including finished deals)
- Parse specs (model, RAM, disk, CPU, GPU) from titles + descriptions
- Assign Geekbench 6 benchmark scores (single-core, multi-core, Metal GPU)
- Assign Geekbench AI scores (CPU/GPU/NPU x 3 precision levels)
- Assign LLM inference benchmarks (Llama2-7B token generation speeds, memory bandwidth)
- Build a web UI to browse and filter deals with benchmarks

## Accomplishments

### Scraping (dev-browser / Playwright)
- Scraped 145 deals across 5 pages from pepper.pl/grupa/macbook-pro
- Date range: "Rok" (Year) filter, includes active + expired ("Wygasla") deals
- Extracted: title, price, old price, date posted, temperature, URL, description snippet
- Used `.thread-price` CSS class for accurate price extraction

### Spec Parsing
- Regex-based parsing from title + description combined text
- Fields: model name, screen size, CPU chip (M1-M5 + Pro/Max), CPU cores, GPU cores, RAM, disk
- Coverage: CPU 145/145, RAM 135/145, Disk 129/145, CPU cores 66/145, GPU cores 72/145
- Core counts are only available when explicitly stated in listing text

### Benchmark Assignment
- **Geekbench 6**: Static lookup table mapping chip+cores -> scores
  - Source: browser.geekbench.com/mac-benchmarks
  - M5 Pro (15-core/18-core) and M5 Max (18-core) added from live search results
  - 145/145 matched
- **Geekbench AI**: Mapped by chip generation (M1-M5)
  - Source: browser.geekbench.com/ai-benchmarks (iPad M-series = same silicon)
  - 9 fields: CPU/GPU/NPU x Single Precision/Half Precision/Quantized
  - 145/145 matched
- **LLM Inference**: From user-provided llm_benchmarks_apple_silicon.json
  - Source: ggerganov benchmarks, Apple ML Research blog, SiliconBench
  - Fields: mem_bw_gbs, gpu_cores, Llama2-7B Q4/Q8/F16 token gen + prompt processing speeds
  - M5/M5 Pro/M5 Max have estimated scores (marked "est")
  - 145/145 matched

### Web UI (index.html)
- Single-page app, dark terminal aesthetic, JetBrains Mono + DM Sans fonts
- Data embedded directly in HTML (no server needed)
- Features:
  - Filter by chip generation (M1-M5), tier (Base/Pro/Max), RAM, disk, max price, text search
  - Sort by price, temperature, GB6 SC/MC, Metal, AI NPU, Mem BW, LLM Q4
  - Card view with benchmark bars + Table view
  - Detail panel overlay with full benchmark breakdown
  - Expired deals shown dimmed
  - Temperature color coding (hot/warm/neutral/cold/frozen)

## File Changes
```
index.html                         - Web UI (125KB, data embedded)
macbook_pro_pepper_benchmarks.json - Final dataset (145 deals, all benchmarks)
macbook_pro_pepper_benchmarks.tsv  - Same data as TSV (30 columns)
macbook_pro_pepper.json            - Raw scraped data (no benchmarks)
macbook_pro_pepper.tsv             - Raw scraped data as TSV
```

## Open Questions / Next Steps
1. **Automation script**: User asked about auto-assigning benchmarks to new listings. Need to build a single script that scrapes -> parses -> joins benchmarks -> outputs JSON/HTML.
2. **M5 Pro Geekbench AI**: No Mac-specific AI benchmark page exists; using iPad scores as proxy (same silicon). Could search individual results like we did for CPU/Metal.
3. **Missing specs**: 10 deals missing RAM, 16 missing disk. Could scrape individual deal pages for more data.
4. **Date normalization**: Dates are relative ("3 d. temu", "2 tyg. temu"). Could convert to absolute dates.

## Discoveries
- pepper.pl uses `.thread-price` class for the main deal price
- `file://` CORS blocks fetch() - embedded data into HTML as fallback
- Geekbench has no Mac-specific AI benchmark page (only general /ai-benchmarks for mobile)
- M5 Pro/Max CPU results available via search (browser.geekbench.com/v6/cpu/search?q=M5+Pro)
- M5 Max is 18 cores (6P+12E), M5 Pro comes in 15-core and 18-core variants
- Mac model IDs: Mac17,6 and Mac17,7 = M5 Max, Mac17,8 and Mac17,9 = M5 Pro

## To Resume
```bash
cd /Users/antekxxx/Coding/mirroir-mcp
# Open UI: open index.html
# Re-scrape: use dev-browser scripts from conversation
# Key question: build automation script for new listings?
```
