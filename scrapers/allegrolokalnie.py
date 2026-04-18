#!/usr/bin/env python3
"""
Scrape Allegro Lokalnie (allegrolokalnie.pl) search results into JSON.

Usage: ./scrapers/allegrolokalnie.py "<search-url>" [--used] [--pages N]

Allegro Lokalnie is a sibling of Allegro with its own local-transaction flow.
It sits behind the same DataDome shield on search pages and returns HTTP 429
on bot HEADs, so Scrappey is required here too.

Output contract: JSON list on stdout, one dict per listing, matching the
shape consumed by `pipeline.py add`.
"""
import json
import pathlib
import re
import sys
import uuid
from urllib.parse import urlparse

from bs4 import BeautifulSoup

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scrapers"))
from scrappey_client import ScrappeyError, fetch  # noqa: E402

# Allegrolokalnie pages are ~30 items. If the last scraped page is still
# this full when we hit the page ceiling, coverage is probably truncated.
FULL_PAGE_THRESHOLD = 25


def _is_offer_href(h: str) -> bool:
    return "/oferta/" in h


def _extract_items(html: str):
    """Return list of (title, url, price) tuples from an allegrolokalnie HTML page.

    Permissive: walks every anchor that points to /oferta/... and heuristically
    pairs it with the nearest price span. If the page shape changes upstream,
    we just return fewer items instead of crashing.
    """
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not _is_offer_href(href):
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 8:
            continue

        if href.startswith("/"):
            href = "https://allegrolokalnie.pl" + href
        href = href.split("?")[0].split("#")[0]

        # Climb up to a container element and search for a price there.
        container = a
        for _ in range(4):
            parent = container.parent
            if parent is None:
                break
            container = parent

        price = ""
        for span in container.select("span, div"):
            text = span.get_text(" ", strip=True)
            if "zł" in text and any(c.isdigit() for c in text) and len(text) < 30:
                price = text
                break

        out.append((title, href, price))
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


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print("Usage: allegrolokalnie.py <search-url> [--used] [--pages N]", file=sys.stderr)
        sys.exit(1)

    raw_url = args[0]
    is_used = "--used" in args
    max_pages = 2
    if "--pages" in args:
        max_pages = int(args[args.index("--pages") + 1])

    base = re.sub(r"[?&]page=\d+", "", raw_url)
    sep = "&" if "?" in base else "?"
    session_id = str(uuid.uuid4())  # reuse Scrappey browser across pages

    seen_urls = set()
    results = []
    last_page_items = 0
    terminated_empty = False
    page_num = 0

    for page_num in range(1, max_pages + 1):
        url = base if page_num == 1 else f"{base}{sep}page={page_num}"
        print(f"[allegrolokalnie] page {page_num}", file=sys.stderr)
        try:
            html = fetch(url, session_id=session_id)
        except ScrappeyError as e:
            print(f"[allegrolokalnie] BLOCKED — Scrappey failed: {e}", file=sys.stderr)
            sys.exit(3)

        items = _extract_items(html)
        last_page_items = len(items)
        new = 0
        for title, u, price in items:
            # Guard: only keep allegrolokalnie URLs (in case the page embeds others)
            host = (urlparse(u).hostname or "").lower()
            if host and "allegrolokalnie" not in host:
                continue
            if u in seen_urls:
                continue
            seen_urls.add(u)
            new += 1
            entry = {
                "title": title,
                "url": u,
                "price": clean_price(price),
                "source": "allegrolokalnie.pl",
                "used": is_used,
            }
            cpu = extract_cpu(u)
            if cpu:
                entry["cpu"] = cpu
            results.append(entry)
        print(f"[allegrolokalnie] {len(items)} found, {new} new, total {len(results)}", file=sys.stderr)
        if new == 0:
            terminated_empty = True
            break

    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))

    # Exit 4 = incomplete coverage (see scrapers/allegro.py for the rationale).
    if not terminated_empty and page_num == max_pages and last_page_items >= FULL_PAGE_THRESHOLD:
        print(f"[allegrolokalnie] INCOMPLETE: ceiling reached with full final page ({last_page_items} items)", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
