#!/usr/bin/env python3
# Scrape OLX.pl listings into JSON for `pipeline.py add`.
# Usage: ./scrapers/olx.py "<search-url>" [--used] [--pages N] [--headful]
#
# Primary: camoufox with persistent profile (.camoufox-profile). Free.
# Fallback: Scrappey (.scrappey-key, ~€0.001/page) if camoufox fails or
# the profile is missing.

import argparse
import json
import pathlib
import re
import sys
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = REPO_ROOT / ".camoufox-profile"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scrapers"))
from scrappey_client import ScrappeyError, fetch as scrappey_fetch  # noqa: E402


def clean_title(t: str) -> str:
    return re.sub(r"\s*\d[\d\s]*z[łl].*$", "", t, flags=re.IGNORECASE).strip()


def clean_price(p: str) -> str:
    p = re.sub(r"[^\d,.]", "", p.split("do negocjacji")[0])
    return p.replace(",", ".").strip(" .")


def _extract_html(html: str, base_url: str):
    """Parse a rendered OLX listing page; returns (items, has_next)."""
    soup = BeautifulSoup(html, "lxml")
    items = []
    for card in soup.select('[data-cy="l-card"]'):
        h4 = card.select_one("h4")
        title = h4.get_text(strip=True) if h4 else ""
        pe = card.select_one('[data-testid="ad-price"]')
        price = pe.get_text(strip=True) if pe else ""
        link = card.select_one('a[href*="/d/oferta/"]')
        raw_url = link.get("href", "") if link else ""
        url = urljoin(base_url, raw_url).split("?")[0]
        if title and url:
            items.append((title, price, url))
    has_next = bool(soup.select_one('[data-cy="pagination-forward"]'))
    return items, has_next


def _scrape_camoufox(base: str, max_pages: int, headful: bool):
    """Yield (page_items, has_next) per page. Raises on any camoufox failure."""
    from camoufox.sync_api import Camoufox  # lazy import — only needed if profile exists

    from ensure_fingerprint import load_or_create as _load_fingerprint  # noqa: E402

    sep = "&" if "?" in base else "?"
    with Camoufox(
        headless=not headful,
        locale="pl-PL",
        persistent_context=True,
        user_data_dir=str(PROFILE),
        fingerprint=_load_fingerprint(),
        i_know_what_im_doing=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8"})
        for n in range(1, max_pages + 1):
            page_url = base if n == 1 else f"{base}{sep}page={n}"
            print(f"[olx] page {n} (camoufox)", file=sys.stderr)
            page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector('[data-cy="l-card"]', timeout=10000)
            time.sleep(1.2)
            html = page.content()
            items, has_next = _extract_html(html, page_url)
            yield items, has_next
            if not has_next:
                return


def _scrape_scrappey(base: str, max_pages: int):
    sep = "&" if "?" in base else "?"
    for n in range(1, max_pages + 1):
        page_url = base if n == 1 else f"{base}{sep}page={n}"
        print(f"[olx] page {n} (scrappey)", file=sys.stderr)
        html = scrappey_fetch(page_url)
        items, has_next = _extract_html(html, page_url)
        yield items, has_next
        if not has_next:
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--used", action="store_true")
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()

    base = args.url
    seen, results = set(), []

    use_camoufox = PROFILE.exists()
    pages_iter = None
    if use_camoufox:
        try:
            pages_iter = list(_scrape_camoufox(base, args.pages, args.headful))
        except Exception as e:  # noqa: BLE001 — any camoufox failure → try Scrappey
            print(f"[olx] camoufox failed: {e} — falling back to Scrappey", file=sys.stderr)
            pages_iter = None

    if pages_iter is None:
        try:
            pages_iter = list(_scrape_scrappey(base, args.pages))
        except ScrappeyError as e:
            print(f"[olx] BLOCKED — Scrappey failed: {e}", file=sys.stderr)
            sys.exit(3)

    for items, _has_next in pages_iter:
        for t, p, u in items:
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
        print(f"[olx] got {len(items)} cards, total {len(results)}", file=sys.stderr)

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
