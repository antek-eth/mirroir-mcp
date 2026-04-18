#!/usr/bin/env python3
# Scrape Allegro.pl listings into JSON for pipeline.py
# Usage: ./scrapers/allegro.py "<search-url>" [--used] [--pages N] [--headful]
#
# Primary: camoufox (stealth Firefox) through a residential proxy.
#   Requires .camoufox-profile/ + .dataimpulse-proxy (or DATAIMPULSE_PROXY env).
# Fallback: Scrappey (.scrappey-key) when camoufox is unavailable.
#
# ⚠ DataDome bypass is environmentally unstable (2026-04-18):
#   - Scrappey's proxy pool is currently flagged for allegro.pl (CODE-0010
#     on every request regardless of country/premium tier)
#   - camoufox + residential-proxy bypass works intermittently — sometimes
#     the JS challenge auto-resolves, other times the page stays captcha'd
#   - When BOTH paths fail, the scraper exits 3 and scrape_all.py records
#     the host as blocked; mark_stale's safety gate then skips its listings
#     so dead Scrappey doesn't cascade into false-positive expiries.
#   Fixes to try when stuck: (a) delete .camoufox-profile/ to reset cookies,
#   (b) rotate DataImpulse IP via their dashboard, (c) contact Scrappey
#   support to rotate their pool.
import json
import pathlib
import re
import sys
import time
import uuid
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scrapers"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scrappey_client import ScrappeyError, fetch as scrappey_fetch  # noqa: E402
from proxy_config import load_proxy  # noqa: E402

PROFILE = REPO_ROOT / ".camoufox-profile"

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


def _fetch_camoufox(urls: list[str], headful: bool) -> list[str]:
    """Yield rendered HTML for each URL via one camoufox session.

    Raises on any failure so the caller can fall back to Scrappey.
    """
    from camoufox.sync_api import Camoufox  # lazy import — only if we try this path
    from ensure_fingerprint import load_or_create as load_fp

    proxy = load_proxy()
    if not proxy:
        raise RuntimeError("no proxy configured — set .dataimpulse-proxy or DATAIMPULSE_PROXY")

    htmls: list[str] = []
    with Camoufox(
        headless=not headful,
        locale="pl-PL",
        persistent_context=True,
        user_data_dir=str(PROFILE),
        fingerprint=load_fp(),
        proxy=proxy,
        geoip=True,
        humanize=True,
        i_know_what_im_doing=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8"})
        for url in urls:
            print(f"[allegro] {url} (camoufox+proxy)", file=sys.stderr)
            # networkidle lets DataDome's async JS challenge complete during
            # goto() itself — avoids synthetic "wait+poll" that can look
            # bot-like. humanize=True handles realistic mouse patterns.
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception:
                # Fall back to domcontentloaded + short settle if networkidle times out.
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(6)
            html = page.content()
            if len(html) < 50000:
                print(f"[allegro] DataDome stuck; last size={len(html)} head={html[:160]!r}",
                      file=sys.stderr)
                raise RuntimeError("camoufox did not resolve DataDome challenge")
            htmls.append(html)
    return htmls


def _fetch_scrappey(urls: list[str]) -> list[str]:
    session_id = str(uuid.uuid4())
    return [scrappey_fetch(u, session_id=session_id) for u in urls]


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print("Usage: allegro.py <search-url> [--used] [--pages N] [--headful]", file=sys.stderr)
        sys.exit(1)

    raw_url = args[0]
    is_used = "--used" in args
    headful = "--headful" in args
    max_pages = 5
    if "--pages" in args:
        max_pages = int(args[args.index("--pages") + 1])

    base = re.sub(r"[?&]p=\d+", "", raw_url)
    sep = "&" if "?" in base else "?"
    page_urls = [base if n == 1 else f"{base}{sep}p={n}" for n in range(1, max_pages + 1)]

    htmls: list[str] = []
    used_path = "scrappey"  # for stderr log
    if PROFILE.exists() and load_proxy():
        try:
            htmls = _fetch_camoufox(page_urls, headful)
            used_path = "camoufox+proxy"
        except Exception as e:  # noqa: BLE001 — any camoufox failure → Scrappey
            print(f"[allegro] camoufox failed: {e} — falling back to Scrappey", file=sys.stderr)
            htmls = []

    if not htmls:
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
