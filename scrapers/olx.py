#!/usr/bin/env python3
# Scrape OLX.pl listings into compact JSON for pipeline.py add
# Usage: ./scrapers/olx.py "<search-url>" [--used] [--pages N] > scraped.json
# Requires: Brave/Chrome running with --remote-debugging-port=9222

import sys, json, re, subprocess, argparse

def run_js(js: str) -> str:
    r = subprocess.run(
        ["dev-browser", "--connect", "http://127.0.0.1:9222"],
        input=js, capture_output=True, text=True, timeout=40
    )
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        return ""
    return r.stdout.strip()

def page_js(page_url: str) -> str:
    return f"""
const p=await browser.getPage("olx");
await p.goto({json.dumps(page_url)},{{waitUntil:"domcontentloaded",timeout:25000}});
await new Promise(r=>setTimeout(r,2000));
const d=await p.evaluate(()=>{{
  const o=[];
  for(const c of document.querySelectorAll('[data-cy="l-card"]')){{
    const t=c.querySelector('h4')?.textContent.trim()||'';
    const pe=c.querySelector('[data-testid="ad-price"]')?.textContent.trim()||'';
    const le=c.querySelector('a[href*="/d/oferta/"]');
    const u=le?.href?.split('?')[0]||'';
    if(t&&u) o.push([t,pe,u]);
  }}
  return o;
}});
const nx=await p.evaluate(()=>!!document.querySelector('[data-cy="pagination-forward"]'));
console.log(JSON.stringify({{d,nx}}));
"""

def clean_title(t: str) -> str:
    return re.sub(r'\s*\d[\d\s]*z[łl].*$', '', t, flags=re.IGNORECASE).strip()

def clean_price(p: str) -> str:
    p = re.sub(r'[^\d,.]', '', p.split('do negocjacji')[0])
    return p.replace(',', '.').strip(' .')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--used", action="store_true")
    ap.add_argument("--pages", type=int, default=10)
    args = ap.parse_args()

    base = args.url
    sep = "&" if "?" in base else "?"
    seen, results = set(), []

    for n in range(1, args.pages + 1):
        page_url = base if n == 1 else f"{base}{sep}page={n}"
        print(f"[olx] page {n}: {page_url}", file=sys.stderr)
        raw = run_js(page_js(page_url))
        if not raw:
            break
        # extract last JSON line (dev-browser may emit other output)
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass
        else:
            print("[olx] no JSON found in output", file=sys.stderr)
            break

        for t, p, u in obj.get("d", []):
            if u in seen:
                continue
            seen.add(u)
            results.append({
                "title": clean_title(t),
                "url": u,
                "price": clean_price(p),
                "source": "olx.pl",
                "used": args.used,
            })

        print(f"[olx] got {len(obj.get('d',[]))} cards, total {len(results)}", file=sys.stderr)
        if not obj.get("nx"):
            break

    print(json.dumps(results, ensure_ascii=False))

if __name__ == "__main__":
    main()
