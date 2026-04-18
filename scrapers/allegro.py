#!/usr/bin/env python3
# Scrape Allegro.pl listings into JSON for pipeline.py
# Usage: ./scrapers/allegro.py "<search-url>" [--used] [--pages N]
#
# Provider: Scrappey (`.scrappey-key`) with `datadomeBypass=true` + Polish
# residential proxy. Confirmed working with Scrappey support 2026-04-19;
# the legacy `datadome` flag is pool-flagged (CODE-0010) and unusable.
# When Scrappey fails the scraper exits 3 and scrape_all.py records the
# host as blocked; mark_stale's safety gate then skips its listings so a
# dead provider doesn't cascade into false-positive expiries.
import json
import pathlib
import re
import sys
import uuid
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scrapers"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scrappey_client import ScrappeyError, fetch as scrappey_fetch  # noqa: E402

# A page with this many items is "full" — if we hit max_pages AND the last
# page was still full, results may have been truncated and coverage is
# incomplete. Allegro pages are ~48 items.
FULL_PAGE_THRESHOLD = 40


def _resolve_href(raw: str) -> str:
    if "/events/clicks" in raw and "redirect=" in raw:
        try:
            params = parse_qs(urlparse(raw).query)
            if params.get("redirect"):
                return unquote(params["redirect"][0])
        except ValueError:
            pass
    return raw


def _is_offer_href(h: str) -> bool:
    return "/oferta/" in h or "/produkt/" in h


def _extract_items(html: str):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for article in soup.select("article"):
        title, url = "", ""
        for a in article.select("a[href]"):
            href = _resolve_href(a.get("href", ""))
            text = a.get_text(strip=True)
            if len(text) > 10 and _is_offer_href(href):
                title, url = text, href
                break
        if not title or not url:
            continue
        url = url.split("#")[0]
        # Keep ?offerId=... for /produkt/ pages, strip all query for /oferta/.
        url = url.split("&")[0] if "?offerId=" in url else url.split("?")[0]

        price = ""
        for span in article.select("span"):
            text = span.get_text(strip=True)
            if "zł" in text and any(c.isdigit() for c in text) and len(text) < 30 and "/" not in text:
                price = text
                break
        out.append((title, url, price))
    return out


def clean_price(p: str) -> str:
    p = re.sub(r"do negocjacji", "", p, flags=re.I).strip()
    return re.sub(r"\s+", " ", p).strip()


def extract_cpu(url: str):
    u = url.lower()
    m = re.search(r"m(\d)[-_]?(pro|max|ultra)", u)
    if m:
        return f"M{m.group(1)} {m.group(2).upper()}"
    m = re.search(r"m(\d)(?![\w])", u)
    if m:
        return f"M{m.group(1)}"
    return None


def _fetch_scrappey(urls: list[str]) -> list[str]:
    session_id = str(uuid.uuid4())
    return [scrappey_fetch(u, session_id=session_id) for u in urls]


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print("Usage: allegro.py <search-url> [--used] [--pages N]", file=sys.stderr)
        sys.exit(1)

    raw_url = args[0]
    is_used = "--used" in args
    max_pages = 5
    if "--pages" in args:
        max_pages = int(args[args.index("--pages") + 1])

    base = re.sub(r"[?&]p=\d+", "", raw_url)
    sep = "&" if "?" in base else "?"
    page_urls = [base if n == 1 else f"{base}{sep}p={n}" for n in range(1, max_pages + 1)]

    used_path = "scrappey"
    try:
        htmls = _fetch_scrappey(page_urls)
    except ScrappeyError as e:
        print(f"[allegro] BLOCKED — Scrappey failed: {e}", file=sys.stderr)
        sys.exit(3)

    seen_urls: set[str] = set()
    results: list[dict] = []
    last_page_items = 0
    terminated_empty = False
    actual_pages = 0

    for page_num, html in enumerate(htmls, start=1):
        actual_pages = page_num
        items = _extract_items(html)
        last_page_items = len(items)
        new = 0
        for title, u, price in items:
            if u in seen_urls:
                continue
            seen_urls.add(u)
            new += 1
            entry = {
                "title": title,
                "url": u,
                "price": clean_price(price),
                "source": "allegro.pl",
                "used": is_used,
            }
            cpu = extract_cpu(u)
            if cpu:
                entry["cpu"] = cpu
            results.append(entry)
        print(f"[allegro] page {page_num} ({used_path}) {len(items)} found, {new} new, total {len(results)}",
              file=sys.stderr)
        if new == 0:
            terminated_empty = True
            break

    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))

    # Exit 4 = incomplete coverage (see header). Safety gate in mark_stale
    # treats this host as "do not expire" for this daily run.
    if not terminated_empty and actual_pages == max_pages and last_page_items >= FULL_PAGE_THRESHOLD:
        print(f"[allegro] INCOMPLETE: ceiling reached with full final page ({last_page_items} items)",
              file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
