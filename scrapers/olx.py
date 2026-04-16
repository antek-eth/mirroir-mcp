#!/usr/bin/env python3
# Scrape OLX.pl listings into compact JSON for pipeline.py add
# Usage: ./scrapers/olx.py "<search-url>" [--used] [--pages N] > scraped.json
# Uses camoufox with the shared persistent profile at .camoufox-profile.

import argparse, json, pathlib, re, sys, time
from camoufox.sync_api import Camoufox

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = REPO_ROOT / ".camoufox-profile"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from ensure_fingerprint import load_or_create as _load_fingerprint


def _extract(page):
    return page.evaluate("""() => {
        const out = [];
        for (const c of document.querySelectorAll('[data-cy="l-card"]')) {
            const t = c.querySelector('h4')?.textContent.trim() || '';
            const pe = c.querySelector('[data-testid="ad-price"]')?.textContent.trim() || '';
            const le = c.querySelector('a[href*="/d/oferta/"]');
            const u = le?.href?.split('?')[0] || '';
            if (t && u) out.push([t, pe, u]);
        }
        const nx = !!document.querySelector('[data-cy="pagination-forward"]');
        return { d: out, nx };
    }""")


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
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()

    if not PROFILE.exists():
        print(f"[olx] missing camoufox profile at {PROFILE}", file=sys.stderr)
        print("[olx] run: python3 scripts/probe_camoufox_persistent.py", file=sys.stderr)
        sys.exit(2)

    base = args.url
    sep = "&" if "?" in base else "?"
    seen, results = set(), []

    with Camoufox(
        headless=not args.headful,
        locale="pl-PL",
        persistent_context=True,
        user_data_dir=str(PROFILE),
        fingerprint=_load_fingerprint(),
        i_know_what_im_doing=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8"})

        for n in range(1, args.pages + 1):
            page_url = base if n == 1 else f"{base}{sep}page={n}"
            print(f"[olx] page {n}", file=sys.stderr)
            try:
                page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector('[data-cy="l-card"]', timeout=10000)
            except Exception as e:
                print(f"[olx] navigation error: {e}", file=sys.stderr)
                break
            time.sleep(1.2)
            obj = _extract(page)
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
            print(f"[olx] got {len(obj.get('d', []))} cards, total {len(results)}", file=sys.stderr)
            if not obj.get("nx"):
                break

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
