#!/usr/bin/env python3
# Scrape Lantre.pl category pages into compact JSON for pipeline.py add
# Usage: ./scrapers/lantre.py "<category-url>" [--pages N]
# Requires: Brave/Chrome running with --remote-debugging-port=9222

import json, subprocess, argparse

JS_BODY = """
const o=[];
const seen=new Set();
for(const b of document.querySelectorAll('button.tocart[data-name][data-price]')){
  const id=b.getAttribute('data-id')||'';
  if(id&&seen.has(id)) continue;
  if(id) seen.add(id);
  const t=b.getAttribute('data-name')||'';
  const p=b.getAttribute('data-price')||'';
  const info=b.closest('.product-item-info')||b.closest('.item')||b.parentElement;
  const u=info?.querySelector('a.product-item-link,a[href*="/apple-"]')?.href||'';
  if(t&&p) o.push([t,p,u]);
}
return JSON.stringify({items:o,next:!!document.querySelector('.pages-item-next')});
"""


def scrape_page(url: str) -> tuple[list, bool]:
    script = (
        f'const page = await browser.getPage("lantre-scrape");\n'
        f'await page.goto({json.dumps(url)}, {{waitUntil:"domcontentloaded",timeout:30000}});\n'
        f'await new Promise(r=>setTimeout(r,2500));\n'
        f'const result = await page.evaluate(()=>{{{JS_BODY.strip()}}});\n'
        f'console.log(result);\n'
    )
    r = subprocess.run(
        ["dev-browser", "--connect", "http://127.0.0.1:9222"],
        input=script, capture_output=True, text=True
    )
    raw = (r.stdout or "").strip()
    try:
        data = json.loads(raw)
        return data.get("items", []), bool(data.get("next"))
    except (json.JSONDecodeError, AttributeError):
        return [], False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="Lantre category URL")
    ap.add_argument("--pages", type=int, default=5, help="Max pages (default 5)")
    args = ap.parse_args()

    base = args.url.rstrip("/").split("?")[0]
    seen_keys: set = set()
    results = []

    for p in range(1, args.pages + 1):
        url = base if p == 1 else f"{base}?p={p}"
        rows, has_next = scrape_page(url)

        for title, price, url_item in rows:
            key = url_item if url_item else f"{title}|{price}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append({"title": title, "url": url_item, "price": price,
                            "source": "lantre.pl", "used": False})

        if not has_next:
            break

    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
