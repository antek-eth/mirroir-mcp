#!/usr/bin/env python3
# Scrape Allegro.pl listings into JSON for pipeline.py
# Usage: ./scrapers/allegro.py "<search-url>" [--used] [--pages N]
#
# Uses Scrappey (https://scrappey.com) to fetch rendered HTML past DataDome.
# API key in .scrappey-key (repo root) or SCRAPPEY_KEY env var.
# No local browser required — runs from any machine with network access.
import json
import pathlib
import re
import sys
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scrapers"))
from scrappey_client import ScrappeyError, fetch  # noqa: E402


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

    seen_urls = set()
    results = []

    for page_num in range(1, max_pages + 1):
        url = base if page_num == 1 else f"{base}{sep}p={page_num}"
        print(f"[allegro] page {page_num}", file=sys.stderr)
        try:
            html = fetch(url)
        except ScrappeyError as e:
            print(f"[allegro] BLOCKED — Scrappey failed: {e}", file=sys.stderr)
            sys.exit(3)

        items = _extract_items(html)
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
        print(f"[allegro] {len(items)} found, {new} new, total {len(results)}", file=sys.stderr)
        if new == 0:
            break

    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
