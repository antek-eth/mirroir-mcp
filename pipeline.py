#!/usr/bin/env python3
"""
MacBook Pro Deal Pipeline
Usage:
  python3 pipeline.py add <file.json>   — Add new listings from JSON file
  python3 pipeline.py rebuild           — Regenerate index.html from database
  python3 pipeline.py clean             — Normalize dates, remove AI fields
  python3 pipeline.py info              — Show database stats
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_FILE = Path(__file__).parent / "macbook_deals.json"
HTML_FILE = Path(__file__).parent / "index.html"

# --- Benchmark Lookup Tables ---
# Geekbench 6 scores by chip (default/most common core config)
GB6 = {
    "M1":       {"gb6_single": 2347, "gb6_multi": 8191,  "gb6_metal": 20759},
    "M1 PRO":   {"gb6_single": 2386, "gb6_multi": 12350, "gb6_metal": 68176},
    "M1 MAX":   {"gb6_single": 2400, "gb6_multi": 12500, "gb6_metal": 96400},
    "M2":       {"gb6_single": 2600, "gb6_multi": 9645,  "gb6_metal": 46470},
    "M2 PRO":   {"gb6_single": 2647, "gb6_multi": 14459, "gb6_metal": 83399},
    "M2 MAX":   {"gb6_single": 2805, "gb6_multi": 14748, "gb6_metal": 140689},
    "M3":       {"gb6_single": 3077, "gb6_multi": 11535, "gb6_metal": 48204},
    "M3 PRO":   {"gb6_single": 3100, "gb6_multi": 15261, "gb6_metal": 79321},
    "M3 MAX":   {"gb6_single": 3102, "gb6_multi": 20935, "gb6_metal": 156455},
    "M4":       {"gb6_single": 3793, "gb6_multi": 14921, "gb6_metal": 57398},
    "M4 PRO":   {"gb6_single": 3851, "gb6_multi": 22438, "gb6_metal": 112257},
    "M4 MAX":   {"gb6_single": 3868, "gb6_multi": 23088, "gb6_metal": 158678},
    "M5":       {"gb6_single": 4225, "gb6_multi": 17453, "gb6_metal": 75898},
    "M5 PRO":   {"gb6_single": 4270, "gb6_multi": 26400, "gb6_metal": 122000},
    "M5 MAX":   {"gb6_single": 4300, "gb6_multi": 28000, "gb6_metal": 210000},
    "M1 ULTRA": {"gb6_single": 2400, "gb6_multi": 17000, "gb6_metal": 155000},
    "M2 ULTRA": {"gb6_single": 2805, "gb6_multi": 20500, "gb6_metal": 195000},
    "M3 ULTRA": {"gb6_single": 3100, "gb6_multi": 28000, "gb6_metal": 240000},
}

# LLM Inference benchmarks by chip (Llama 2 7B)
LLM = {
    "M1":       {"mem_bw_gbs": 68,  "llm_gpu_cores": 8,  "llama2_7b_q4_tg": 14.15, "llama2_7b_q4_pp": 117.96, "llama2_7b_q8_tg": 7.91,  "llama2_7b_f16_tg": None},
    "M1 PRO":   {"mem_bw_gbs": 200, "llm_gpu_cores": 16, "llama2_7b_q4_tg": 36.41, "llama2_7b_q4_pp": 266.25, "llama2_7b_q8_tg": 22.34, "llama2_7b_f16_tg": 12.75},
    "M1 MAX":   {"mem_bw_gbs": 400, "llm_gpu_cores": 32, "llama2_7b_q4_tg": 60.0,  "llama2_7b_q4_pp": 530.0,  "llama2_7b_q8_tg": 39.0,  "llama2_7b_f16_tg": 23.0},
    "M2":       {"mem_bw_gbs": 100, "llm_gpu_cores": 10, "llama2_7b_q4_tg": 21.91, "llama2_7b_q4_pp": 179.57, "llama2_7b_q8_tg": 12.21, "llama2_7b_f16_tg": 6.72},
    "M2 PRO":   {"mem_bw_gbs": 200, "llm_gpu_cores": 19, "llama2_7b_q4_tg": 38.86, "llama2_7b_q4_pp": 341.19, "llama2_7b_q8_tg": 23.01, "llama2_7b_f16_tg": 13.06},
    "M2 MAX":   {"mem_bw_gbs": 400, "llm_gpu_cores": 38, "llama2_7b_q4_tg": 65.95, "llama2_7b_q4_pp": 671.31, "llama2_7b_q8_tg": 41.83, "llama2_7b_f16_tg": 24.65},
    "M3":       {"mem_bw_gbs": 100, "llm_gpu_cores": 10, "llama2_7b_q4_tg": 21.34, "llama2_7b_q4_pp": 186.75, "llama2_7b_q8_tg": 12.27, "llama2_7b_f16_tg": None},
    "M3 PRO":   {"mem_bw_gbs": 150, "llm_gpu_cores": 18, "llama2_7b_q4_tg": 30.74, "llama2_7b_q4_pp": 341.67, "llama2_7b_q8_tg": 17.53, "llama2_7b_f16_tg": 9.89},
    "M3 MAX":   {"mem_bw_gbs": 400, "llm_gpu_cores": 40, "llama2_7b_q4_tg": 66.31, "llama2_7b_q4_pp": 759.70, "llama2_7b_q8_tg": 42.75, "llama2_7b_f16_tg": 25.09},
    "M4":       {"mem_bw_gbs": 120, "llm_gpu_cores": 10, "llama2_7b_q4_tg": 24.11, "llama2_7b_q4_pp": 221.29, "llama2_7b_q8_tg": 13.54, "llama2_7b_f16_tg": 7.43},
    "M4 PRO":   {"mem_bw_gbs": 273, "llm_gpu_cores": 20, "llama2_7b_q4_tg": 50.74, "llama2_7b_q4_pp": 439.78, "llama2_7b_q8_tg": 30.69, "llama2_7b_f16_tg": 17.18},
    "M4 MAX":   {"mem_bw_gbs": 546, "llm_gpu_cores": 40, "llama2_7b_q4_tg": 83.06, "llama2_7b_q4_pp": 885.68, "llama2_7b_q8_tg": 54.05, "llama2_7b_f16_tg": 31.64},
    "M5":       {"mem_bw_gbs": 154, "llm_gpu_cores": 10, "llama2_7b_q4_tg": 29.6,  "llama2_7b_q4_pp": None,   "llama2_7b_q8_tg": None,  "llama2_7b_f16_tg": None},
    "M5 PRO":   {"mem_bw_gbs": 307, "llm_gpu_cores": 20, "llama2_7b_q4_tg": 57.0,  "llama2_7b_q4_pp": None,   "llama2_7b_q8_tg": None,  "llama2_7b_f16_tg": None},
    "M5 MAX":   {"mem_bw_gbs": 546, "llm_gpu_cores": 40, "llama2_7b_q4_tg": 85.0,  "llama2_7b_q4_pp": None,   "llama2_7b_q8_tg": None,  "llama2_7b_f16_tg": None},
    "M1 ULTRA": {"mem_bw_gbs": 800, "llm_gpu_cores": 48, "llama2_7b_q4_tg": 110.0, "llama2_7b_q4_pp": None,   "llama2_7b_q8_tg": None,  "llama2_7b_f16_tg": None},
    "M2 ULTRA": {"mem_bw_gbs": 800, "llm_gpu_cores": 60, "llama2_7b_q4_tg": 130.0, "llama2_7b_q4_pp": None,   "llama2_7b_q8_tg": None,  "llama2_7b_f16_tg": None},
    "M3 ULTRA": {"mem_bw_gbs": 800, "llm_gpu_cores": 60, "llama2_7b_q4_tg": 145.0, "llama2_7b_q4_pp": None,   "llama2_7b_q8_tg": None,  "llama2_7b_f16_tg": None},
}

# Polish month names for date parsing
PL_MONTHS = {
    "sty": 1, "lut": 2, "mar": 3, "kwi": 4, "maj": 5, "cze": 6,
    "lip": 7, "sie": 8, "wrz": 9, "paź": 10, "lis": 11, "gru": 12,
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5,
    "czerwca": 6, "lipca": 7, "sierpnia": 8, "września": 9,
    "października": 10, "listopada": 11, "grudnia": 12,
}


# --- Spec Parser ---

def parse_cpu(text):
    """Extract Apple Silicon chip from text. Returns e.g. 'M4 PRO' or 'M2 ULTRA'."""
    text = text.upper()
    m = re.search(r'M(\d)\s*(MAX|PRO|ULTRA)?', text)
    if m:
        gen = m.group(1)
        tier = m.group(2) or ""
        return f"M{gen} {tier}".strip()
    return ""


def parse_ram(text):
    """Extract RAM size. Returns e.g. '24GB'."""
    upper = text.upper()
    m = re.search(r'(\d+)\s*GB\s*(?:RAM|UNIFIED|PAMIĘCI|PAM)', upper)
    if m:
        return f"{m.group(1)}GB"
    # Common RAM sizes explicitly labeled with GB
    m = re.search(r'\b(8|16|18|24|32|36|48|64|96|128|192)\s*GB\b', upper)
    if m:
        return f"{m.group(1)}GB"
    # Bare RAM value after chip model (e.g. "M1 MAX 64 1TB" — common in Allegro titles)
    m = re.search(r'M\d\s*(?:MAX|PRO|ULTRA)?\s+(\d{1,3})(?:\s|/)', upper)
    if m:
        val = int(m.group(1))
        if val in (8, 16, 18, 24, 32, 36, 48, 64, 96, 128, 192):
            return f"{val}GB"
    return ""


def parse_disk(text):
    """Extract disk size. Returns e.g. '1TB' or '512GB'."""
    upper = text.upper()
    # Look for TB first
    m = re.search(r'(\d+)\s*TB', upper)
    if m:
        return f"{m.group(1)}TB"
    # Look for SSD-labeled GB values that are disk-sized (>=256GB, not RAM)
    m = re.search(r'(\d{3,4})\s*GB\s*(?:SSD|DYSK|NVME|STORAGE)', upper)
    if m and int(m.group(1)) >= 256:
        return f"{m.group(1)}GB"
    # Look for any large GB value (>=256 is always disk for Macs, RAM maxes at 192)
    m = re.search(r'\b(\d{3,4})\s*GB\b', upper)
    if m and int(m.group(1)) >= 256:
        return f"{m.group(1)}GB"
    # Fallback: bare 256 or 512 without unit
    m = re.search(r'\b(256|512)\b', upper)
    if m:
        return f"{m.group(1)}GB"
    return ""


def parse_screen(text):
    """Extract screen size. Returns e.g. '14' or '16'."""
    # Match digits with optional comma/dot decimal before quote (e.g. 16,2" or 14.2")
    m = re.search(r'(\d{2})[,.]?\d*\s*[\"\u201c\u201d\u201e\u2033\'`\u2019\u2018]', text)
    if m:
        val = int(m.group(1))
        if val in (13, 14, 16):
            return str(val)
    # Match "pro 16" or "macbook 16" pattern (bare number after model name)
    m = re.search(r'(?:pro|macbook|book)\s+(\d{2})\b', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if val in (13, 14, 16):
            return str(val)
    # Match "16-cal" / "16 cali" / "16 inch"
    m = re.search(r'(\d{2})\s*[-]?\s*(?:cal|inch)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if val in (13, 14, 16):
            return str(val)
    return ""


def parse_cpu_cores(text):
    """Extract CPU core count. Returns e.g. '12-core'."""
    text = text.upper()
    m = re.search(r'(\d+)\s*[-]?\s*(?:CORE|RDZENI)\s*(?:CPU)?', text)
    if m:
        return f"{m.group(1)}-core"
    m = re.search(r'(\d+)\s*CPU', text)
    if m:
        return f"{m.group(1)}-core"
    return ""


def parse_gpu_cores(text):
    """Extract GPU core count. Returns e.g. '16-core'."""
    text = text.upper()
    m = re.search(r'(\d+)\s*[-]?\s*(?:CORE|RDZENI)\s*GPU', text)
    if m:
        return f"{m.group(1)}-core"
    # Look for pattern like "10CPU 10GPU" or "10C CPU, 10C GPU"
    m = re.search(r'(\d+)\s*[-]?\s*C(?:ORE)?\s*GPU', text)
    if m:
        return f"{m.group(1)}-core"
    return ""


def parse_price(text):
    """Parse Polish price string to float. Returns None if unparseable."""
    if not text:
        return None
    # Remove currency and whitespace
    cleaned = text.replace("zł", "").replace("PLN", "").replace(" ", "").replace("\xa0", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_specs(title, description=""):
    """Parse all specs from title + description text."""
    text = f"{title} {description}".strip()
    cpu = parse_cpu(text)
    ram = parse_ram(text)
    disk = parse_disk(text)
    screen = parse_screen(text)
    cpu_cores = parse_cpu_cores(text)
    gpu_cores = parse_gpu_cores(text)

    # Detect form factor from title
    tl = text.lower()
    if 'studio' in tl or 'mac studio' in tl:
        screen = 'Studio'
    elif 'mac mini' in tl or 'macmini' in tl:
        screen = 'Mini'
    elif not screen and cpu:
        # Infer screen size from chip if not found
        if cpu in ("M1", "M2"):
            screen = "13"
        else:
            screen = "14"  # default for M3+

    # Build model name
    if screen == 'Studio':
        model = f'Mac Studio {cpu}' if cpu else 'Mac Studio'
    elif screen == 'Mini':
        model = f'Mac Mini {cpu}' if cpu else 'Mac Mini'
    else:
        # Detect Air vs Pro from title
        is_air = 'air' in tl
        macbook_type = 'MacBook Air' if is_air else 'MacBook Pro'
        model = f'{macbook_type} {screen}"' if screen else macbook_type
        if cpu:
            model += f" {cpu}"

    return {
        "model": model,
        "cpu": cpu,
        "ram": ram,
        "disk": disk,
        "screen": screen,
        "cpuCores": cpu_cores,
        "gpuCores": gpu_cores,
    }


# --- Benchmark Assignment ---

def assign_benchmarks(cpu):
    """Return benchmark dict for a given chip name."""
    benchmarks = {}
    gb6 = GB6.get(cpu, {})
    llm = LLM.get(cpu, {})
    benchmarks.update(gb6)
    for k, v in llm.items():
        benchmarks[k] = v if v is not None else ""
    return benchmarks


# --- Date Normalization ---

def normalize_date(date_str, reference_date=None):
    """Convert Polish relative/absolute date to ISO format."""
    if not date_str:
        return ""
    if reference_date is None:
        reference_date = datetime.now()

    text = date_str.lower().strip()

    # Already ISO format
    if re.match(r'\d{4}-\d{2}-\d{2}', text):
        return text[:10]

    # Relative: "X d. temu" (X days ago)
    m = re.search(r'(\d+)\s*d\.?\s*temu', text)
    if m:
        days = int(m.group(1))
        return (reference_date - timedelta(days=days)).strftime("%Y-%m-%d")

    # Relative: "X godz. temu" (X hours ago)
    m = re.search(r'(\d+)\s*godz\.?\s*temu', text)
    if m:
        return reference_date.strftime("%Y-%m-%d")

    # Relative: "X min temu"
    m = re.search(r'(\d+)\s*min\.?\s*temu', text)
    if m:
        return reference_date.strftime("%Y-%m-%d")

    # Relative: "X tyg. temu" (X weeks ago)
    m = re.search(r'(\d+)\s*tyg\.?\s*temu', text)
    if m:
        weeks = int(m.group(1))
        return (reference_date - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

    # Absolute: "2 lut", "11 sty", "Wygasło 2 lut"
    m = re.search(r'(\d{1,2})\s+(\w+)', text)
    if m:
        day = int(m.group(1))
        month_str = m.group(2)[:3]
        month = PL_MONTHS.get(month_str)
        if month:
            year = reference_date.year
            try:
                d = datetime(year, month, day)
                # If the date is in the future, it's probably last year
                if d > reference_date:
                    d = datetime(year - 1, month, day)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                pass

    return ""


# --- Database Management ---

def load_db():
    """Load the deal database."""
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return []


def save_db(deals):
    """Save the deal database."""
    DB_FILE.write_text(json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8")


def make_dedup_key(deal):
    """Create a deduplication key for a deal."""
    if deal.get("url"):
        return deal["url"]
    # Fallback: unique combo of model + specs + price + date
    return f"{deal.get('model','')}|{deal.get('cpu','')}|{deal.get('ram','')}|{deal.get('disk','')}|{deal.get('price','')}|{deal.get('oldPrice','')}|{deal.get('datePosted','')}|{deal.get('temperature','')}"


def process_raw_listings(raw_listings, source=""):
    """Process raw scraped listings into enriched deals."""
    processed = []
    for raw in raw_listings:
        title = raw.get("title", "")
        description = raw.get("description", "")

        # Parse specs
        specs = parse_specs(title, description)

        # If raw already has parsed fields, prefer those
        cpu = raw.get("cpu") or specs["cpu"]
        ram = raw.get("ram") or specs["ram"]
        disk = raw.get("disk") or specs["disk"]
        screen = raw.get("screen") or specs["screen"]
        cpu_cores = raw.get("cpuCores") or specs["cpuCores"]
        gpu_cores = raw.get("gpuCores") or raw.get("gpu") or specs["gpuCores"]
        model = raw.get("model") or specs["model"]

        if not cpu:
            print(f"  SKIP (no CPU found): {title[:60]}")
            continue

        # Assign benchmarks
        benchmarks = assign_benchmarks(cpu)

        # Normalize date (default to today for store listings)
        date_raw = raw.get("datePosted", "")
        date_norm = normalize_date(date_raw, datetime(2026, 4, 7))
        if not date_norm:
            date_norm = datetime.now().strftime("%Y-%m-%d")

        # Build deal entry
        deal = {
            "title": title,
            "model": model,
            "cpu": cpu,
            "ram": ram,
            "disk": disk,
            "screen": screen,
            "cpuCores": cpu_cores,
            "gpuCores": gpu_cores,
            "price": raw.get("price", ""),
            "oldPrice": raw.get("oldPrice", ""),
            "priceNum": parse_price(raw.get("price", "")),
            "datePosted": date_raw,
            "date": date_norm,
            "temperature": raw.get("temperature", ""),
            "url": raw.get("url", ""),
            "source": raw.get("source", source),
            "expired": raw.get("expired", False),
            "used": raw.get("used", False),
            "broken": raw.get("broken", False),
        }
        deal.update(benchmarks)
        processed.append(deal)

    return processed


def merge_deals(existing, new_deals):
    """Merge new deals into existing, deduplicating by URL."""
    seen = {make_dedup_key(d) for d in existing}
    added = 0
    for deal in new_deals:
        key = make_dedup_key(deal)
        if key not in seen:
            existing.append(deal)
            seen.add(key)
            added += 1
    return added


# --- HTML Generator ---

def generate_html(deals):
    """Generate the config-grouped HTML dashboard."""
    data_json = json.dumps(deals, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_json)
    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"  Generated {HTML_FILE} ({len(deals)} deals, {HTML_FILE.stat().st_size // 1024}KB)")


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MacBook Pro // Deal Explorer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0a0c;--bg2:#111114;--bg3:#18181c;--bg4:#222228;
  --fg:#e8e8ec;--fg2:#a0a0aa;--fg3:#68687a;
  --accent:#4ade80;--accent2:#22c55e;--accent-dim:rgba(74,222,128,.08);
  --hot:#ef4444;--warm:#f97316;--cold:#3b82f6;--frozen:#6366f1;
  --border:#2a2a32;--border2:#3a3a44;
  --font-mono:'JetBrains Mono',monospace;--font-sans:'DM Sans',sans-serif;
  --radius:6px;
}
html{font-size:13px;background:var(--bg);color:var(--fg);font-family:var(--font-sans)}
body{min-height:100vh;background:var(--bg);overflow-x:hidden}
body::before{content:'';position:fixed;top:0;left:0;right:0;height:300px;background:linear-gradient(180deg,rgba(74,222,128,.03) 0%,transparent 100%);pointer-events:none;z-index:0}
.container{max-width:1600px;margin:0 auto;padding:24px 20px;position:relative;z-index:1}
header{display:flex;align-items:flex-end;justify-content:space-between;padding:20px 0 32px;border-bottom:1px solid var(--border);margin-bottom:24px}
.logo{display:flex;align-items:center;gap:12px}
.logo-mark{width:32px;height:32px;background:var(--accent);border-radius:6px;display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-weight:700;font-size:14px;color:var(--bg)}
h1{font-family:var(--font-mono);font-size:22px;font-weight:600;letter-spacing:-.5px}
h1 span{color:var(--accent);font-weight:300}
.header-meta{font-family:var(--font-mono);font-size:11px;color:var(--fg3);text-align:right;line-height:1.6}
.header-meta strong{color:var(--fg2)}

.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px;align-items:center}
.filter-group{display:flex;align-items:center;gap:6px}
.filter-label{font-family:var(--font-mono);font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--fg3);white-space:nowrap}
.chip-filters{display:flex;gap:4px;flex-wrap:wrap}
.chip-btn{font-family:var(--font-mono);font-size:11px;padding:4px 10px;border:1px solid var(--border);background:transparent;color:var(--fg2);border-radius:100px;cursor:pointer;transition:all .15s;white-space:nowrap}
.chip-btn:hover{border-color:var(--fg3);color:var(--fg)}
.chip-btn.active{background:var(--accent-dim);border-color:var(--accent);color:var(--accent)}
select.filter-select{font-family:var(--font-mono);font-size:11px;padding:4px 8px;border:1px solid var(--border);background:var(--bg2);color:var(--fg2);border-radius:var(--radius);cursor:pointer;appearance:auto}
input.filter-input{font-family:var(--font-mono);font-size:11px;padding:4px 8px;border:1px solid var(--border);background:var(--bg2);color:var(--fg);border-radius:var(--radius);width:120px}
input.filter-input:focus{outline:none;border-color:var(--accent)}
input.filter-input::placeholder{color:var(--fg3)}
.divider{width:1px;height:20px;background:var(--border);margin:0 8px}
.results-count{font-family:var(--font-mono);font-size:11px;color:var(--fg3);margin-left:auto}
.results-count strong{color:var(--accent)}

.sort-bar{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
.sort-label{font-family:var(--font-mono);font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--fg3);margin-right:4px}
.sort-btn{font-family:var(--font-mono);font-size:10px;padding:3px 8px;border:1px solid transparent;background:transparent;color:var(--fg3);border-radius:4px;cursor:pointer;transition:all .15s;white-space:nowrap}
.sort-btn:hover{color:var(--fg2)}
.sort-btn.active{border-color:var(--border2);color:var(--accent);background:var(--accent-dim)}
.sort-btn .arrow{margin-left:3px;font-size:9px}

.configs-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px}
.config-card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;transition:all .2s}
.config-card:hover{border-color:var(--border2);box-shadow:0 8px 24px rgba(0,0,0,.3)}

.config-header{padding:16px 16px 12px;display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.config-title{flex:1}
.config-chip{font-family:var(--font-mono);font-size:13px;font-weight:600;padding:2px 8px;border-radius:4px;white-space:nowrap;display:inline-block;margin-bottom:6px}
.config-chip.m1{background:rgba(99,102,241,.15);color:#818cf8}
.config-chip.m2{background:rgba(59,130,246,.15);color:#60a5fa}
.config-chip.m3{background:rgba(34,197,94,.15);color:#4ade80}
.config-chip.m4{background:rgba(249,115,22,.15);color:#fb923c}
.config-chip.m5{background:rgba(239,68,68,.15);color:#f87171}
.config-name{font-family:var(--font-sans);font-size:15px;font-weight:600;color:var(--fg);line-height:1.3}
.config-specs{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}
.spec-tag{font-family:var(--font-mono);font-size:10px;padding:2px 6px;background:var(--bg3);border-radius:3px;color:var(--fg2)}

.config-price{text-align:right;white-space:nowrap}
.price-range{font-family:var(--font-mono);font-size:18px;font-weight:700;color:var(--fg)}
.price-range .sep{color:var(--fg3);font-weight:300;font-size:13px;margin:0 2px}
.listing-count{font-family:var(--font-mono);font-size:10px;color:var(--fg3);margin-top:2px}

.bench-section{padding:0 16px 12px}
.bench-row{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.bench-label{font-family:var(--font-mono);font-size:10px;color:var(--fg3);width:50px;text-align:right;flex-shrink:0}
.bench-bar-bg{flex:1;height:6px;background:var(--bg4);border-radius:3px;overflow:hidden}
.bench-bar{height:100%;border-radius:3px;transition:width .3s}
.bench-bar.cpu{background:linear-gradient(90deg,#3b82f6,#60a5fa)}
.bench-bar.metal{background:linear-gradient(90deg,#d97706,#fbbf24)}
.bench-bar.llm{background:linear-gradient(90deg,#db2777,#f472b6)}
.bench-bar.bw{background:linear-gradient(90deg,#7c3aed,#a78bfa)}
.bench-value{font-family:var(--font-mono);font-size:10px;color:var(--fg2);width:55px;text-align:right;flex-shrink:0}

.listings-toggle{width:100%;padding:8px 16px;background:var(--bg3);border:none;border-top:1px solid var(--border);color:var(--fg3);font-family:var(--font-mono);font-size:10px;cursor:pointer;text-align:left;transition:all .15s;display:flex;justify-content:space-between;align-items:center}
.listings-toggle:hover{background:var(--bg4);color:var(--fg2)}
.listings-toggle .arrow{transition:transform .2s}
.listings-toggle.open .arrow{transform:rotate(180deg)}

.listings-panel{max-height:0;overflow:hidden;transition:max-height .3s ease}
.listings-panel.open{max-height:600px;overflow-y:auto}
.listing-row{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;border-top:1px solid var(--border);font-size:11px;gap:8px}
.listing-row:hover{background:var(--bg3)}
.listing-row.expired{opacity:.5}
.listing-info{flex:1;min-width:0}
.listing-title{font-family:var(--font-sans);color:var(--fg2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.listing-meta{font-family:var(--font-mono);font-size:10px;color:var(--fg3);margin-top:2px}
.listing-meta .source{color:var(--accent);opacity:.7}
.tag-used{font-family:var(--font-mono);font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(251,191,36,.15);color:#fbbf24;margin-left:4px}
.listing-price{font-family:var(--font-mono);font-weight:600;color:var(--fg);white-space:nowrap;margin-left:8px}
.listing-price.old{color:var(--fg3);text-decoration:line-through;font-weight:400;font-size:10px}
.listing-link{color:var(--accent);text-decoration:none;font-family:var(--font-mono);font-size:11px;flex-shrink:0;margin-left:8px}
.listing-link:hover{text-decoration:underline}

.detail-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:none;justify-content:flex-end;backdrop-filter:blur(4px)}
.detail-overlay.open{display:flex}
.detail-panel{width:480px;max-width:90vw;background:var(--bg2);border-left:1px solid var(--border);padding:32px 24px;overflow-y:auto}
.detail-close{position:absolute;top:12px;right:12px;background:none;border:none;color:var(--fg3);font-size:24px;cursor:pointer;padding:4px 8px;border-radius:4px}
.detail-close:hover{background:var(--bg4);color:var(--fg)}
.detail-chip-badge{display:inline-block;margin-bottom:8px}
.detail-title{font-size:18px;font-weight:600;margin-bottom:8px;line-height:1.3}
.detail-subtitle{font-family:var(--font-mono);font-size:11px;color:var(--fg3);margin-bottom:20px}
.detail-section-title{font-family:var(--font-mono);font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--fg3);margin:16px 0 8px;padding-top:12px;border-top:1px solid var(--border)}
.detail-bench-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px}
.detail-bench{background:var(--bg3);padding:10px;border-radius:var(--radius);text-align:center}
.detail-bench-label{font-family:var(--font-mono);font-size:9px;color:var(--fg3);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.detail-bench-val{font-family:var(--font-mono);font-size:16px;font-weight:600}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}
.detail-stat{background:var(--bg3);padding:10px;border-radius:var(--radius)}
.detail-stat-label{font-family:var(--font-mono);font-size:9px;color:var(--fg3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.detail-stat-value{font-family:var(--font-mono);font-size:16px;font-weight:600}
.detail-stat-value small{font-size:10px;color:var(--fg3);font-weight:400;margin-left:2px}

.view-toggle{display:flex;gap:2px;background:var(--bg2);border-radius:var(--radius);padding:2px;border:1px solid var(--border)}
.view-btn{font-family:var(--font-mono);font-size:10px;padding:4px 10px;border:none;background:transparent;color:var(--fg3);cursor:pointer;border-radius:4px;transition:all .15s}
.view-btn.active{background:var(--bg4);color:var(--fg)}

.config-table{width:100%;border-collapse:collapse;font-size:12px}
.config-table thead{position:sticky;top:0;z-index:2}
.config-table th{font-family:var(--font-mono);font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--fg3);padding:8px 10px;text-align:left;background:var(--bg2);border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer}
.config-table th:hover{color:var(--fg2)}
.config-table th.active{color:var(--accent)}
.config-table td{padding:6px 10px;border-bottom:1px solid var(--border);font-family:var(--font-mono);white-space:nowrap}
.config-table tr:hover{background:var(--bg3)}
.config-table .price-cell{font-weight:600;color:var(--fg)}
.config-table .chip-cell{font-weight:600;padding:1px 6px;border-radius:4px;font-size:10px;display:inline-block}
.bar-cell{position:relative;min-width:80px}
.bar-cell .bar-bg{position:absolute;left:0;top:0;bottom:0;border-radius:3px;opacity:.18;z-index:0}
.bar-cell .bar-val{position:relative;z-index:1}

.empty-state{text-align:center;padding:60px 20px;color:var(--fg3)}
.empty-state .icon{font-size:48px;margin-bottom:16px;opacity:.3}

@media(max-width:600px){
  .configs-grid{grid-template-columns:1fr}
  .config-header{flex-direction:column}
  .config-price{text-align:left}
  .detail-panel{width:100vw}
}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">
      <div class="logo-mark">M</div>
      <div>
        <h1>MacBook Pro <span>//</span> Deal Explorer</h1>
      </div>
    </div>
    <div class="header-meta" id="dataInfo"></div>
  </header>

  <div class="filters">
    <div class="filter-group">
      <span class="filter-label">Chip</span>
      <div class="chip-filters" id="chipFilters"></div>
    </div>
    <div class="divider"></div>
    <div class="filter-group">
      <span class="filter-label">Tier</span>
      <div class="chip-filters" id="tierFilters"></div>
    </div>
    <div class="divider"></div>
    <div class="filter-group">
      <span class="filter-label">RAM</span>
      <div class="chip-filters" id="ramFilters"></div>
    </div>
    <div class="filter-group">
      <span class="filter-label">Source</span>
      <div class="chip-filters" id="sourceFilters"></div>
    </div>
    <div class="filter-group">
      <span class="filter-label">Model</span>
      <div class="chip-filters" id="modelFilters"></div>
    </div>
    <div class="filter-group">
      <span class="filter-label">Screen</span>
      <div class="chip-filters" id="screenFilters"></div>
    </div>
    <div class="filter-group">
      <span class="filter-label">Disk</span>
      <select class="filter-select" id="diskFilter"><option value="">All</option></select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Max</span>
      <input class="filter-input" id="priceMax" type="text" placeholder="max price">
    </div>
    <div class="filter-group">
      <input class="filter-input" id="searchInput" type="text" placeholder="search..." style="width:160px">
    </div>
    <div class="view-toggle">
      <button class="view-btn" data-view="cards" onclick="setView('cards')">Cards</button>
      <button class="view-btn active" data-view="table" onclick="setView('table')">Table</button>
    </div>
    <span class="results-count" id="resultsCount"></span>
  </div>

  <div class="sort-bar" id="sortBar">
    <span class="sort-label">Sort</span>
  </div>

  <div class="configs-grid" id="configsGrid" style="display:none"></div>
  <div id="tableView" style="overflow-x:auto"></div>

  <div class="detail-overlay" id="detailOverlay">
    <div class="detail-panel" id="detailPanel"></div>
  </div>
</div>

<script>
const DATA = __DATA_PLACEHOLDER__;

let activeChips = new Set();
let activeTiers = new Set();
let activeRams = new Set();
let activeSources = new Set();
let activeModels = new Set();
let activeScreens = new Set();
let hiddenListings = new Set(JSON.parse(localStorage.getItem('hiddenListings') || '[]'));

function hideListing(url) {
  hiddenListings.add(url);
  localStorage.setItem('hiddenListings', JSON.stringify([...hiddenListings]));
  applyFilters();
  closeDetail();
}
function unhideAll() {
  hiddenListings.clear();
  localStorage.setItem('hiddenListings', '[]');
  applyFilters();
}
let currentSort = { key: 'priceMin', dir: 'asc' };
let currentView = 'table';
let configs = [];
let filtered = [];

const SORT_OPTIONS = [
  { key: 'priceMin', label: 'Min Price' },
  { key: 'listingCount', label: 'Listings' },
  { key: 'gb6_single', label: 'GB6 SC' },
  { key: 'gb6_multi', label: 'GB6 MC' },
  { key: 'gb6_metal', label: 'Metal' },
  { key: 'mem_bw_gbs', label: 'Mem BW' },
  { key: 'llm_q4', label: 'LLM Q4' },
  { key: 'toksPerKPLN', label: 'toks/1kPLN' },
];

const MAX_GB6_SINGLE = 4300;
const MAX_GB6_MULTI = 30000;
const MAX_METAL = 230000;
const MAX_LLM = 95;
const MAX_BW = 620;

function parsePrice(p) {
  if (!p) return null;
  const n = parseFloat(p.toString().replace(/\s/g, '').replace('zł', '').replace(',', '.'));
  return isNaN(n) ? null : n;
}
function parseLLM(v) {
  if (!v && v !== 0) return 0;
  const n = parseFloat(String(v));
  return isNaN(n) ? 0 : n;
}
function chipGen(cpu) { return cpu.match(/M(\d)/)?.[1] || '0'; }
function chipTier(cpu) {
  if (/ULTRA/.test(cpu)) return 'ULTRA';
  if (/MAX/.test(cpu)) return 'MAX';
  if (/PRO/.test(cpu)) return 'PRO';
  return 'Base';
}
function chipClass(cpu) { return 'm' + chipGen(cpu); }
function fmtNum(n) {
  if (!n && n !== 0) return '-';
  return Number(n).toLocaleString('pl-PL');
}
function fmtPrice(n) {
  if (!n) return '?';
  return n.toLocaleString('pl-PL') + ' zl';
}
function pct(val, max) { return Math.min(100, Math.max(1, (val / max) * 100)); }

function buildConfigs() {
  const map = {};
  DATA.forEach(d => {
    const cpu = d.cpu || '';
    const ram = d.ram || '';
    const disk = d.disk || '';
    const screen = d.screen || '';
    if (!cpu) return;
    const key = [screen, cpu, ram, disk].join('|');
    if (!map[key]) {
      map[key] = {
        key, cpu, ram, disk, screen,
        gb6_single: d.gb6_single || 0,
        gb6_multi: d.gb6_multi || 0,
        gb6_metal: d.gb6_metal || 0,
        mem_bw_gbs: d.mem_bw_gbs || 0,
        llm_q4: parseLLM(d.llama2_7b_q4_tg),
        llm_q4_pp: parseLLM(d.llama2_7b_q4_pp),
        llm_q8: parseLLM(d.llama2_7b_q8_tg),
        llm_f16: parseLLM(d.llama2_7b_f16_tg),
        llm_gpu_cores: d.llm_gpu_cores || 0,
        listings: [],
        prices: [],
      };
    }
    const price = d.priceNum || parsePrice(d.price);
    const oldPrice = parsePrice(d.oldPrice);
    map[key].listings.push({
      title: d.title || d.model || '',
      price: price,
      oldPrice: oldPrice,
      priceStr: d.price || '',
      oldPriceStr: d.oldPrice || '',
      url: d.url || '',
      source: d.source || '',
      date: d.date || d.datePosted || '',
      datePosted: d.datePosted || '',
      expired: d.expired || /wygasł/i.test(d.datePosted || ''),
      used: d.used || false,
      broken: d.broken || false,
    });
    if (price) map[key].prices.push(price);
    if (!price && oldPrice) map[key].prices.push(oldPrice);
  });

  return Object.values(map).map(c => {
    c.listings.sort((a, b) => (a.price || Infinity) - (b.price || Infinity));
    c.prices.sort((a, b) => a - b);
    c.priceMin = c.prices[0] || null;
    c.priceMax = c.prices[c.prices.length - 1] || null;
    c.listingCount = c.listings.length;
    c.toksPerKPLN = (c.llm_q4 && c.priceMin) ? Math.round((c.llm_q4 / c.priceMin) * 1000 * 100) / 100 : 0;
    return c;
  });
}

function initFilters() {
  const chips = [...new Set(configs.map(c => 'M' + chipGen(c.cpu)))].sort();
  const tiers = [...new Set(configs.map(c => chipTier(c.cpu)))].sort((a,b) => {
    const order = { Base: 0, PRO: 1, MAX: 2, ULTRA: 3 };
    return (order[a]||0) - (order[b]||0);
  });
  const rams = [...new Set(configs.map(c => c.ram).filter(Boolean))].sort((a,b) => parseInt(a)-parseInt(b));
  const screenOrder = {'13':0,'14':1,'16':2,'Studio':3,'Mini':4};
  const screens = [...new Set(configs.map(c => c.screen).filter(Boolean))].sort((a,b) => (screenOrder[a]||9)-(screenOrder[b]||9));
  const disks = [...new Set(configs.map(c => c.disk).filter(Boolean))].sort((a,b) => {
    const va = a.includes('TB') ? parseInt(a)*1024 : parseInt(a);
    const vb = b.includes('TB') ? parseInt(b)*1024 : parseInt(b);
    return va - vb;
  });

  const chipEl = document.getElementById('chipFilters');
  chips.forEach(c => {
    const btn = document.createElement('button');
    btn.className = 'chip-btn';
    btn.textContent = c;
    btn.onclick = () => { btn.classList.toggle('active'); activeChips.has(c) ? activeChips.delete(c) : activeChips.add(c); applyFilters(); };
    chipEl.appendChild(btn);
  });
  const tierEl = document.getElementById('tierFilters');
  tiers.forEach(t => {
    const btn = document.createElement('button');
    btn.className = 'chip-btn';
    btn.textContent = t;
    btn.onclick = () => { btn.classList.toggle('active'); activeTiers.has(t) ? activeTiers.delete(t) : activeTiers.add(t); applyFilters(); };
    tierEl.appendChild(btn);
  });
  const ramEl = document.getElementById('ramFilters');
  rams.forEach(r => {
    const btn = document.createElement('button');
    btn.className = 'chip-btn';
    btn.textContent = r;
    btn.onclick = () => { btn.classList.toggle('active'); activeRams.has(r) ? activeRams.delete(r) : activeRams.add(r); applyFilters(); };
    ramEl.appendChild(btn);
  });
  const sources = [...new Set(configs.flatMap(c => c.listings.map(l => l.source)).filter(Boolean))].sort();
  const sourceEl = document.getElementById('sourceFilters');
  sources.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'chip-btn';
    btn.textContent = s;
    btn.onclick = () => { btn.classList.toggle('active'); activeSources.has(s) ? activeSources.delete(s) : activeSources.add(s); applyFilters(); };
    sourceEl.appendChild(btn);
  });
  const models = [...new Set(configs.map(c => c.model).filter(Boolean))].sort();
  const modelEl = document.getElementById('modelFilters');
  models.forEach(m => {
    const btn = document.createElement('button');
    btn.className = 'chip-btn';
    btn.textContent = m;
    btn.onclick = () => { btn.classList.toggle('active'); activeModels.has(m) ? activeModels.delete(m) : activeModels.add(m); applyFilters(); };
    modelEl.appendChild(btn);
  });
  const screenEl = document.getElementById('screenFilters');
  screens.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'chip-btn';
    btn.textContent = /^\d+$/.test(s) ? s + '"' : s;
    btn.dataset.val = s;
    btn.onclick = () => { btn.classList.toggle('active'); activeScreens.has(s) ? activeScreens.delete(s) : activeScreens.add(s); applyFilters(); };
    screenEl.appendChild(btn);
  });
  const diskSel = document.getElementById('diskFilter');
  disks.forEach(d => { const o = document.createElement('option'); o.value = d; o.textContent = d; diskSel.appendChild(o); });

  diskSel.onchange = applyFilters;
  document.getElementById('priceMax').oninput = applyFilters;
  document.getElementById('searchInput').oninput = applyFilters;

  const sortBar = document.getElementById('sortBar');
  SORT_OPTIONS.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'sort-btn' + (currentSort.key === opt.key ? ' active' : '');
    btn.innerHTML = opt.label + '<span class="arrow">' + (currentSort.key === opt.key ? (currentSort.dir === 'desc' ? ' &#9660;' : ' &#9650;') : '') + '</span>';
    btn.onclick = () => {
      if (currentSort.key === opt.key) currentSort.dir = currentSort.dir === 'desc' ? 'asc' : 'desc';
      else { currentSort.key = opt.key; currentSort.dir = opt.key === 'priceMin' ? 'asc' : 'desc'; }
      applyFilters();
    };
    sortBar.appendChild(btn);
  });
}

function pushURL() {
  const p = new URLSearchParams();
  if (activeChips.size) p.set('chip', [...activeChips].join(','));
  if (activeTiers.size) p.set('tier', [...activeTiers].join(','));
  if (activeRams.size) p.set('ram', [...activeRams].join(','));
  if (activeScreens.size) p.set('screen', [...activeScreens].join(','));
  if (activeSources.size) p.set('source', [...activeSources].join(','));
  if (activeModels.size) p.set('model', [...activeModels].join(','));
  const disk = document.getElementById('diskFilter').value;
  if (disk) p.set('disk', disk);
  const maxP = document.getElementById('priceMax').value.replace(/\s/g, '');
  if (maxP) p.set('maxprice', maxP);
  const search = document.getElementById('searchInput').value;
  if (search) p.set('q', search);
  if (currentSort.key !== 'priceMin' || currentSort.dir !== 'asc') p.set('sort', currentSort.key + '.' + currentSort.dir);
  if (currentView !== 'table') p.set('view', currentView);
  const qs = p.toString();
  history.replaceState(null, '', qs ? '?' + qs : location.pathname);
}

function loadURL() {
  const p = new URLSearchParams(location.search);
  if (p.has('chip')) p.get('chip').split(',').forEach(c => activeChips.add(c));
  if (p.has('tier')) p.get('tier').split(',').forEach(t => activeTiers.add(t));
  if (p.has('ram')) p.get('ram').split(',').forEach(r => activeRams.add(r));
  if (p.has('screen')) p.get('screen').split(',').forEach(s => activeScreens.add(s));
  if (p.has('source')) p.get('source').split(',').forEach(s => activeSources.add(s));
  if (p.has('model')) p.get('model').split(',').forEach(m => activeModels.add(m));
  if (p.has('disk')) document.getElementById('diskFilter').value = p.get('disk');
  if (p.has('maxprice')) document.getElementById('priceMax').value = p.get('maxprice');
  if (p.has('q')) document.getElementById('searchInput').value = p.get('q');
  if (p.has('sort')) { const [k,d] = p.get('sort').split('.'); currentSort = {key:k, dir:d||'asc'}; }
  if (p.has('view')) currentView = p.get('view');
  // Sync button states
  document.querySelectorAll('#chipFilters .chip-btn').forEach(b => { if (activeChips.has(b.textContent)) b.classList.add('active'); });
  document.querySelectorAll('#tierFilters .chip-btn').forEach(b => { if (activeTiers.has(b.textContent)) b.classList.add('active'); });
  document.querySelectorAll('#ramFilters .chip-btn').forEach(b => { if (activeRams.has(b.textContent)) b.classList.add('active'); });
  document.querySelectorAll('#screenFilters .chip-btn').forEach(b => { if (activeScreens.has(b.dataset.val)) b.classList.add('active'); });
  document.querySelectorAll('#sourceFilters .chip-btn').forEach(b => { if (activeSources.has(b.textContent)) b.classList.add('active'); });
  document.querySelectorAll('#modelFilters .chip-btn').forEach(b => { if (activeModels.has(b.textContent)) b.classList.add('active'); });
  document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === currentView));
}

function applyFilters() {
  const disk = document.getElementById('diskFilter').value;
  const maxPrice = parseInt(document.getElementById('priceMax').value.replace(/\s/g, '')) || Infinity;
  const search = document.getElementById('searchInput').value.toLowerCase();

  filtered = configs.map(c => {
    {
      const visible = c.listings.filter(l => !hiddenListings.has(l.url) && !l.broken);
      if (visible.length === 0) return null;
      if (visible.length < c.listings.length) {
        c = Object.assign({}, c, {
          listings: visible,
          listingCount: visible.length,
          prices: visible.map(l => l.price).filter(Boolean).sort((a,b) => a-b),
        });
        c.priceMin = c.prices[0] || null;
        c.priceMax = c.prices[c.prices.length - 1] || null;
        c.toksPerKPLN = (c.llm_q4 && c.priceMin) ? Math.round((c.llm_q4 / c.priceMin) * 1000 * 100) / 100 : 0;
      }
    }
    return c;
  }).filter(c => {
    if (!c) return false;
    if (activeChips.size && !activeChips.has('M' + chipGen(c.cpu))) return false;
    if (activeTiers.size && !activeTiers.has(chipTier(c.cpu))) return false;
    if (activeRams.size && !activeRams.has(c.ram)) return false;
    if (activeScreens.size && !activeScreens.has(c.screen)) return false;
    if (activeSources.size && !c.listings.some(l => activeSources.has(l.source))) return false;
    if (activeModels.size && !activeModels.has(c.model)) return false;
    if (disk && c.disk !== disk) return false;
    if (c.priceMin && c.priceMin > maxPrice) return false;
    if (search) {
      const hay = [c.cpu, c.ram, c.disk, c.screen].join(' ').toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });

  filtered.sort((a, b) => {
    let va = a[currentSort.key] || 0;
    let vb = b[currentSort.key] || 0;
    if (currentSort.key === 'priceMin') { va = va || Infinity; vb = vb || Infinity; }
    return currentSort.dir === 'desc' ? vb - va : va - vb;
  });

  document.querySelectorAll('.sort-btn').forEach((btn, i) => {
    const opt = SORT_OPTIONS[i];
    btn.className = 'sort-btn' + (currentSort.key === opt.key ? ' active' : '');
    btn.innerHTML = opt.label + '<span class="arrow">' + (currentSort.key === opt.key ? (currentSort.dir === 'desc' ? ' &#9660;' : ' &#9650;') : '') + '</span>';
  });

  const totalListings = filtered.reduce((s, c) => s + c.listingCount, 0);
  const hiddenCount = hiddenListings.size;
  document.getElementById('resultsCount').innerHTML = '<strong>' + filtered.length + '</strong> configs &middot; ' + totalListings + ' listings' + (hiddenCount ? ' &middot; <span style="color:var(--fg3)">' + hiddenCount + ' hidden</span> <button onclick="unhideAll()" style="background:none;border:1px solid rgba(255,255,255,.15);color:var(--accent);cursor:pointer;font-size:10px;padding:1px 6px;border-radius:3px;margin-left:4px">unhide all</button>' : '');
  pushURL();
  render();
}

function setView(v) {
  currentView = v;
  document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  pushURL();
  render();
}

function renderTable() {
  const wrap = document.getElementById('tableView');
  if (!filtered.length) { wrap.innerHTML = '<div class="empty-state"><div class="icon">&#128187;</div><p>No configs match your filters</p></div>'; return; }
  wrap.innerHTML = `<table class="config-table"><thead><tr>
    <th>Chip</th><th>Screen</th><th>RAM</th><th>Disk</th>
    <th>Min Price</th><th>Max Price</th><th>Listings</th>
    <th>GB6 SC</th><th>GB6 MC</th><th>Metal</th>
    <th>Mem BW</th><th>Q4 t/s</th><th>toks/1kPLN</th>
  </tr></thead><tbody>${filtered.map((c, ci) => {
    const cc = chipClass(c.cpu);
    return `<tr onclick="showDetail(${ci})" style="cursor:pointer">
      <td><span class="chip-cell config-chip ${cc}">${c.cpu}</span></td>
      <td>${c.screen ? (/^\d+$/.test(c.screen) ? c.screen + '"' : c.screen) : '-'}</td>
      <td>${c.ram || '-'}</td><td>${c.disk || '-'}</td>
      <td class="price-cell">${c.priceMin ? fmtNum(c.priceMin) : '-'}</td>
      <td class="price-cell" style="color:var(--fg2)">${c.priceMax && c.priceMax !== c.priceMin ? fmtNum(c.priceMax) : '-'}</td>
      <td>${c.listingCount}</td>
      <td>${fmtNum(c.gb6_single)}</td><td>${fmtNum(c.gb6_multi)}</td><td>${fmtNum(c.gb6_metal)}</td>
      <td>${c.mem_bw_gbs || '-'} GB/s</td>
      <td class="bar-cell"><div class="bar-bg" style="width:${pct(c.llm_q4, MAX_LLM)}%;background:linear-gradient(90deg,#db2777,#f472b6)"></div><span class="bar-val">${c.llm_q4 || '-'}</span></td>
      <td class="bar-cell"><div class="bar-bg" style="width:${c.toksPerKPLN ? pct(c.toksPerKPLN, Math.max(...filtered.map(x=>x.toksPerKPLN||0))) : 0}%;background:linear-gradient(90deg,#059669,#4ade80)"></div><span class="bar-val" style="color:var(--accent)">${c.toksPerKPLN || '-'}</span></td>
    </tr>`;
  }).join('')}</tbody></table>`;
}

function render() {
  const grid = document.getElementById('configsGrid');
  const table = document.getElementById('tableView');
  grid.style.display = currentView === 'cards' ? 'grid' : 'none';
  table.style.display = currentView === 'table' ? 'block' : 'none';
  if (currentView === 'table') { renderTable(); return; }
  if (!filtered.length) {
    grid.innerHTML = '<div class="empty-state"><div class="icon">&#128187;</div><p>No configs match your filters</p></div>';
    return;
  }
  grid.innerHTML = filtered.map((c, ci) => {
    const cc = chipClass(c.cpu);
    const label = (c.screen ? c.screen + '" ' : '') + c.cpu;
    const llmVal = c.llm_q4;
    return `
    <div class="config-card">
      <div class="config-header">
        <div class="config-title">
          <span class="config-chip ${cc}">${c.cpu}</span>
          <div class="config-name">MacBook Pro ${c.screen ? c.screen + '"' : ''}</div>
          <div class="config-specs">
            ${c.ram ? `<span class="spec-tag">${c.ram}</span>` : '<span class="spec-tag" style="opacity:.4">RAM?</span>'}
            ${c.disk ? `<span class="spec-tag">${c.disk}</span>` : '<span class="spec-tag" style="opacity:.4">Disk?</span>'}
            ${c.mem_bw_gbs ? `<span class="spec-tag">${c.mem_bw_gbs} GB/s</span>` : ''}
          </div>
        </div>
        <div class="config-price">
          ${c.priceMin ? `<div class="price-range">${fmtNum(c.priceMin)}${c.priceMax && c.priceMax !== c.priceMin ? '<span class="sep"> - </span>' + fmtNum(c.priceMax) : ''} <span style="font-size:11px;font-weight:400;color:var(--fg3)">zl</span></div>` : '<div class="price-range" style="color:var(--fg3)">-</div>'}
          <div class="listing-count">${c.listingCount} listing${c.listingCount !== 1 ? 's' : ''}</div>
        </div>
      </div>
      <div class="bench-section">
        <div class="bench-row">
          <span class="bench-label">GB6 SC</span>
          <div class="bench-bar-bg"><div class="bench-bar cpu" style="width:${pct(c.gb6_single,MAX_GB6_SINGLE)}%"></div></div>
          <span class="bench-value">${fmtNum(c.gb6_single)}</span>
        </div>
        <div class="bench-row">
          <span class="bench-label">GB6 MC</span>
          <div class="bench-bar-bg"><div class="bench-bar cpu" style="width:${pct(c.gb6_multi,MAX_GB6_MULTI)}%"></div></div>
          <span class="bench-value">${fmtNum(c.gb6_multi)}</span>
        </div>
        <div class="bench-row">
          <span class="bench-label">Metal</span>
          <div class="bench-bar-bg"><div class="bench-bar metal" style="width:${pct(c.gb6_metal,MAX_METAL)}%"></div></div>
          <span class="bench-value">${fmtNum(c.gb6_metal)}</span>
        </div>
        <div class="bench-row">
          <span class="bench-label">Q4 t/s</span>
          <div class="bench-bar-bg"><div class="bench-bar llm" style="width:${pct(llmVal,MAX_LLM)}%"></div></div>
          <span class="bench-value">${llmVal || '-'}</span>
        </div>
        <div class="bench-row">
          <span class="bench-label">BW</span>
          <div class="bench-bar-bg"><div class="bench-bar bw" style="width:${pct(c.mem_bw_gbs,MAX_BW)}%"></div></div>
          <span class="bench-value">${c.mem_bw_gbs || '-'} GB/s</span>
        </div>
      </div>
      <button class="listings-toggle" onclick="toggleListings(this, ${ci})">
        <span>Show ${c.listingCount} listing${c.listingCount !== 1 ? 's' : ''}</span>
        <span class="arrow">&#9660;</span>
      </button>
      <div class="listings-panel" id="listings-${ci}">
        ${c.listings.map(l => `
          <div class="listing-row${l.expired ? ' expired' : ''}">
            <div class="listing-info">
              <div class="listing-title">${l.title || 'MacBook Pro ' + c.cpu}</div>
              <div class="listing-meta">${l.date || l.datePosted || ''} ${l.source ? '<span class="source">' + l.source + '</span>' : ''}${l.used ? '<span class="tag-used">used</span>' : ''}</div>
            </div>
            ${l.price ? `<span class="listing-price">${fmtNum(l.price)} zl</span>` : (l.oldPrice ? `<span class="listing-price old">${fmtNum(l.oldPrice)} zl</span>` : '')}
            ${l.url ? `<a class="listing-link" href="${l.url}" target="_blank">&#8599;</a>` : ''}
          </div>
        `).join('')}
      </div>
    </div>`;
  }).join('');
}

function toggleListings(btn, idx) {
  const panel = document.getElementById('listings-' + idx);
  btn.classList.toggle('open');
  panel.classList.toggle('open');
}

function showDetail(ci) {
  const c = filtered[ci];
  if (!c) return;
  const cc = chipClass(c.cpu);
  const panel = document.getElementById('detailPanel');
  panel.innerHTML = `
    <button class="detail-close" onclick="closeDetail()">&times;</button>
    <span class="detail-chip-badge config-chip ${cc}">${c.cpu}</span>
    <div class="detail-title">MacBook Pro ${c.screen ? c.screen + '"' : ''} ${c.cpu} ${c.ram ? '/ ' + c.ram : ''} ${c.disk ? '/ ' + c.disk : ''}</div>
    <div class="detail-subtitle">${c.listingCount} listings &middot; ${c.priceMin ? fmtPrice(c.priceMin) + (c.priceMax !== c.priceMin ? ' - ' + fmtPrice(c.priceMax) : '') : 'no price data'}</div>
    <div class="detail-section-title">Geekbench 6</div>
    <div class="detail-bench-grid">
      <div class="detail-bench"><div class="detail-bench-label">Single-Core</div><div class="detail-bench-val" style="color:#60a5fa">${fmtNum(c.gb6_single)}</div></div>
      <div class="detail-bench"><div class="detail-bench-label">Multi-Core</div><div class="detail-bench-val" style="color:#60a5fa">${fmtNum(c.gb6_multi)}</div></div>
      <div class="detail-bench"><div class="detail-bench-label">Metal GPU</div><div class="detail-bench-val" style="color:#fbbf24">${fmtNum(c.gb6_metal)}</div></div>
    </div>
    <div class="detail-section-title">LLM Inference (Llama 2 7B)</div>
    <div class="detail-grid">
      <div class="detail-stat"><div class="detail-stat-label">Mem Bandwidth</div><div class="detail-stat-value">${c.mem_bw_gbs || '-'}<small>GB/s</small></div></div>
      <div class="detail-stat"><div class="detail-stat-label">GPU Cores</div><div class="detail-stat-value">${c.llm_gpu_cores || '-'}</div></div>
    </div>
    <div class="detail-bench-grid" style="grid-template-columns:1fr 1fr">
      <div class="detail-bench"><div class="detail-bench-label">Q4 Token Gen</div><div class="detail-bench-val" style="color:#f472b6">${c.llm_q4 || '-'}<small> t/s</small></div></div>
      <div class="detail-bench"><div class="detail-bench-label">Q4 Prompt</div><div class="detail-bench-val" style="color:#f472b6">${c.llm_q4_pp || '-'}<small> t/s</small></div></div>
      <div class="detail-bench"><div class="detail-bench-label">Q8 Token Gen</div><div class="detail-bench-val" style="color:#f472b6">${c.llm_q8 || '-'}<small> t/s</small></div></div>
      <div class="detail-bench"><div class="detail-bench-label">F16 Token Gen</div><div class="detail-bench-val" style="color:#f472b6">${c.llm_f16 || '-'}<small> t/s</small></div></div>
    </div>
    <div class="detail-section-title">Listings (${c.listingCount})</div>
    <div style="display:flex;flex-direction:column;gap:2px">
      ${c.listings.map(l => `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:var(--bg3);border-radius:4px;gap:8px${l.expired ? ';opacity:.5' : ''}">
        <div style="flex:1;min-width:0">
          <div style="font-family:var(--font-sans);font-size:12px;color:var(--fg2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${l.title}</div>
          <div style="font-family:var(--font-mono);font-size:10px;color:var(--fg3);margin-top:2px">${l.date || ''}${l.source ? ' &middot; <span style="color:var(--accent);opacity:.7">' + l.source + '</span>' : ''}${l.used ? ' <span style="font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(251,191,36,.15);color:#fbbf24">used</span>' : ''}${l.broken ? ' <span style="font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(239,68,68,.15);color:#ef4444">broken</span>' : ''}</div>
        </div>
        <div style="font-family:var(--font-mono);font-weight:600;font-size:12px;white-space:nowrap">${l.price ? fmtNum(l.price) + ' zl' : '-'}</div>
        ${l.url ? '<a href="' + l.url + '" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none;font-family:var(--font-mono);font-size:11px;flex-shrink:0" onclick="event.stopPropagation()">link &rarr;</a>' : ''}
        ${l.url ? '<button onclick="event.stopPropagation();hideListing(\'' + l.url.replace(/'/g, "\\'") + '\')" style="background:none;border:1px solid rgba(255,255,255,.1);color:var(--fg3);cursor:pointer;font-size:10px;padding:2px 6px;border-radius:3px;flex-shrink:0" title="Hide this listing">hide</button>' : ''}
      </div>`).join('')}
    </div>
  `;
  document.getElementById('detailOverlay').classList.add('open');
}

function closeDetail() { document.getElementById('detailOverlay').classList.remove('open'); }
document.getElementById('detailOverlay').onclick = e => { if (e.target === e.currentTarget) closeDetail(); };
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

function init() {
  const sources = [...new Set(DATA.map(d => d.source).filter(Boolean))];
  document.getElementById('dataInfo').innerHTML = '<strong>' + DATA.length + '</strong> deals &middot; ' + (sources.length ? sources.join(', ') : 'pepper.pl');
  configs = buildConfigs();
  initFilters();
  loadURL();
  applyFilters();
}
init();
</script>
</body>
</html>'''


# --- CLI ---

def cmd_add(filepath):
    """Add listings from a JSON file."""
    raw = json.loads(Path(filepath).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = [raw]
    print(f"Processing {len(raw)} raw listings...")

    source = ""
    if raw and raw[0].get("source"):
        source = raw[0]["source"]

    processed = process_raw_listings(raw, source)
    print(f"  Parsed {len(processed)} valid listings")

    db = load_db()
    added = merge_deals(db, processed)
    save_db(db)
    print(f"  Added {added} new, {len(processed) - added} duplicates skipped")
    print(f"  Database: {len(db)} total deals")

    generate_html(db)


def cmd_rebuild():
    """Regenerate HTML from current database."""
    db = load_db()
    if not db:
        print("Database is empty. Use 'add' first.")
        return
    generate_html(db)


def cmd_clean():
    """Clean existing data: normalize dates, remove AI fields, fix prices."""
    db = load_db()
    if not db:
        print("Database is empty.")
        return

    ref_date = datetime(2026, 4, 7)
    ai_fields = ["ai_cpu_sp", "ai_cpu_hp", "ai_cpu_q", "ai_gpu_sp", "ai_gpu_hp",
                  "ai_gpu_q", "ai_npu_sp", "ai_npu_hp", "ai_npu_q"]

    for d in db:
        # Remove AI fields
        for f in ai_fields:
            d.pop(f, None)

        # Normalize dates
        if d.get("datePosted") and not d.get("date"):
            d["date"] = normalize_date(d["datePosted"], ref_date)

        # Ensure priceNum
        if not d.get("priceNum") and d.get("price"):
            d["priceNum"] = parse_price(d["price"])

        # Ensure source
        if not d.get("source"):
            if d.get("url") and "pepper.pl" in d["url"]:
                d["source"] = "pepper.pl"

        # Ensure expired flag
        if "expired" not in d:
            d["expired"] = bool(re.search(r'wygasł', d.get("datePosted", ""), re.I))

        # Re-assign benchmarks (GB6 + LLM only)
        cpu = d.get("cpu", "")
        if cpu:
            benchmarks = assign_benchmarks(cpu)
            d.update(benchmarks)

        # Parse screen if missing
        if not d.get("screen"):
            model = d.get("model", "")
            m = re.search(r'(\d{2})["\.]', model)
            if m and int(m.group(1)) in (13, 14, 16):
                d["screen"] = m.group(1)
            elif d.get("title"):
                d["screen"] = parse_screen(d["title"])

    save_db(db)
    print(f"Cleaned {len(db)} deals")
    generate_html(db)


def cmd_info():
    """Show database stats."""
    db = load_db()
    print(f"Database: {DB_FILE}")
    print(f"Total deals: {len(db)}")
    if not db:
        return

    chips = {}
    sources = {}
    for d in db:
        cpu = d.get("cpu", "?")
        chips[cpu] = chips.get(cpu, 0) + 1
        src = d.get("source", "?")
        sources[src] = sources.get(src, 0) + 1

    print(f"\nBy chip:")
    for k in sorted(chips):
        print(f"  {k:12s} {chips[k]:3d}")
    print(f"\nBy source:")
    for k in sorted(sources):
        print(f"  {k:20s} {sources[k]:3d}")

    with_price = sum(1 for d in db if d.get("priceNum"))
    with_url = sum(1 for d in db if d.get("url"))
    with_title = sum(1 for d in db if d.get("title"))
    print(f"\nWith price: {with_price}/{len(db)}")
    print(f"With URL:   {with_url}/{len(db)}")
    print(f"With title: {with_title}/{len(db)}")


def cmd_migrate():
    """Migrate old format data to new format."""
    old_file = Path(__file__).parent / "macbook_pro_pepper_benchmarks.json"
    if not old_file.exists():
        print("No old data to migrate.")
        return

    old_data = json.loads(old_file.read_text(encoding="utf-8"))
    print(f"Migrating {len(old_data)} deals from old format...")

    db = load_db()
    ref_date = datetime(2026, 4, 7)
    ai_fields = ["ai_cpu_sp", "ai_cpu_hp", "ai_cpu_q", "ai_gpu_sp", "ai_gpu_hp",
                  "ai_gpu_q", "ai_npu_sp", "ai_npu_hp", "ai_npu_q"]

    migrated = []
    for d in old_data:
        deal = dict(d)

        # Remove AI fields
        for f in ai_fields:
            deal.pop(f, None)

        # Add source
        if not deal.get("source"):
            deal["source"] = "pepper.pl"

        # Normalize date
        deal["date"] = normalize_date(deal.get("datePosted", ""), ref_date)

        # Parse price
        deal["priceNum"] = parse_price(deal.get("price"))

        # Parse screen
        if not deal.get("screen"):
            model = deal.get("model", "")
            m = re.search(r'(\d{2})["\.]', model)
            if m and int(m.group(1)) in (13, 14, 16):
                deal["screen"] = m.group(1)
            else:
                deal["screen"] = parse_screen(deal.get("title", "") or model)

        # Expired flag
        deal["expired"] = bool(re.search(r'wygasł', deal.get("datePosted", ""), re.I))

        # Rename gpu -> gpuCores for consistency
        if "gpu" in deal and "gpuCores" not in deal:
            deal["gpuCores"] = deal.pop("gpu")

        # Re-assign clean benchmarks
        cpu = deal.get("cpu", "")
        if cpu:
            benchmarks = assign_benchmarks(cpu)
            deal.update(benchmarks)

        migrated.append(deal)

    added = merge_deals(db, migrated)
    save_db(db)
    print(f"  Migrated {added} new deals ({len(migrated) - added} duplicates)")
    print(f"  Database: {len(db)} total")
    generate_html(db)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) >= 3:
        cmd_add(sys.argv[2])
    elif cmd == "rebuild":
        cmd_rebuild()
    elif cmd == "clean":
        cmd_clean()
    elif cmd == "info":
        cmd_info()
    elif cmd == "migrate":
        cmd_migrate()
    else:
        print(__doc__)
        sys.exit(1)
