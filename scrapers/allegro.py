#!/usr/bin/env python3
# Scrape Allegro.pl listings into JSON for pipeline.py
# Usage: ./scrapers/allegro.py "<search-url>" [--used] [--pages N] [--headful]
#
# Uses camoufox with a persistent Firefox profile at .camoufox-profile.
# First-time setup (interactive, to solve DataDome CONFIRM once):
#     python3 scripts/probe_camoufox_persistent.py
# After that the profile keeps the DataDome session for daily headless runs.
import json, pathlib, random, re, sys, time
from camoufox.sync_api import Camoufox

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = REPO_ROOT / ".camoufox-profile"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from ensure_fingerprint import load_or_create as _load_fingerprint


def _human_scroll(page):
    page.evaluate("""
        () => new Promise((resolve) => {
            const maxScroll = document.body.scrollHeight * 0.75;
            let pos = 0;
            const step = () => {
                pos += Math.floor(Math.random() * 250) + 100;
                window.scrollTo(0, pos);
                if (pos < maxScroll) setTimeout(step, Math.floor(Math.random() * 200) + 80);
                else resolve();
            };
            step();
        })
    """)


def _extract_items(page):
    return page.evaluate("""
        () => {
            const resolveHref = (raw) => {
                let href = raw || '';
                if (href.includes('/events/clicks') && href.includes('redirect=')) {
                    try {
                        const r = new URL(href).searchParams.get('redirect');
                        if (r) href = decodeURIComponent(r);
                    } catch (e) {}
                }
                return href;
            };
            const isOfferHref = (h) => (
                h.includes('/oferta/') || h.includes('/produkt/')
            );
            const out = [];
            for (const a of document.querySelectorAll('article')) {
                let t = '', u = '';
                for (const l of a.querySelectorAll('a[href]')) {
                    const href = resolveHref(l.href);
                    const text = l.textContent.trim();
                    if (text.length > 10 && isOfferHref(href)) {
                        t = text; u = href; break;
                    }
                }
                if (!t || !u) continue;
                u = u.split('#')[0];
                u = u.includes('?offerId=')
                    ? u.split('&')[0]   // keep ?offerId=... for /produkt/ pages
                    : u.split('?')[0];  // strip all query for /oferta/ pages
                let p = '';
                for (const s of a.querySelectorAll('span')) {
                    const x = s.textContent.trim();
                    if (x.includes('zł') && /\\d/.test(x) && x.length < 30 && !x.includes('/')) {
                        p = x; break;
                    }
                }
                out.push([t, u, p]);
            }
            return out;
        }
    """)


def clean_price(p):
    p = re.sub(r'do negocjacji', '', p, flags=re.I).strip()
    p = re.sub(r'\s+', ' ', p).strip()
    return p


def extract_cpu(url):
    m = re.search(r'm(\d)[-_]?(pro|max|ultra)', url.lower())
    if m:
        return f"M{m.group(1)} {m.group(2).upper()}"
    m = re.search(r'm(\d)(?![\w])', url.lower())
    if m:
        return f"M{m.group(1)}"
    return None


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        print("Usage: allegro.py <search-url> [--used] [--pages N] [--headful]", file=sys.stderr)
        sys.exit(1)

    raw_url = args[0]
    is_used = '--used' in args
    headful = '--headful' in args
    max_pages = 5
    if '--pages' in args:
        idx = args.index('--pages')
        max_pages = int(args[idx + 1])

    if not PROFILE.exists():
        print(f"[allegro] missing camoufox profile at {PROFILE}", file=sys.stderr)
        print("[allegro] run: python3 scripts/probe_camoufox_persistent.py  (solve CONFIRM once)", file=sys.stderr)
        sys.exit(2)

    base = re.sub(r'[?&]p=\d+', '', raw_url)
    sep = '&' if '?' in base else '?'

    seen_urls = set()
    results = []

    with Camoufox(
        headless=not headful,
        locale="pl-PL",
        persistent_context=True,
        user_data_dir=str(PROFILE),
        fingerprint=_load_fingerprint(),
        i_know_what_im_doing=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_extra_http_headers({
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        })

        for page_num in range(1, max_pages + 1):
            url = base if page_num == 1 else f"{base}{sep}p={page_num}"
            print(f"[allegro] page {page_num}", file=sys.stderr)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_selector('article', timeout=15000)
            except Exception as e:
                blocked = page.evaluate("() => document.documentElement.outerHTML.includes('captcha-delivery')")
                if blocked:
                    print("[allegro] BLOCKED — DataDome session lost. Run: python3 scripts/probe_camoufox_persistent.py", file=sys.stderr)
                    sys.exit(3)
                print(f"[allegro] navigation error: {e}", file=sys.stderr)
                break

            time.sleep(random.uniform(0.8, 2.3))
            _human_scroll(page)
            time.sleep(random.uniform(0.3, 0.9))

            items = _extract_items(page)
            new = 0
            for title, u, price in items:
                if u in seen_urls:
                    continue
                seen_urls.add(u)
                new += 1
                entry = {
                    'title': title,
                    'url': u,
                    'price': clean_price(price),
                    'source': 'allegro.pl',
                    'used': is_used,
                }
                cpu = extract_cpu(u)
                if cpu:
                    entry['cpu'] = cpu
                results.append(entry)
            print(f"[allegro] {len(items)} found, {new} new, total {len(results)}", file=sys.stderr)
            if new == 0:
                break

    print(json.dumps(results, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
