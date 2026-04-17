#!/usr/bin/env python3
"""
Auto-outlier detection: listings with anomalously high toksPerKPLN are usually
broken (bez matrycy, na części, iCloud locked). Visits each flagged listing
via the Scrappey pipeline (same path as the scrapers), scans page text for
Polish/English red-flag keywords, and auto-hides matches so they stop skewing
the price-to-performance view.

Runs between scrape and rebuild in scripts/daily.sh.
"""
import math
import pathlib
import random
import re
import sys
import time
from datetime import datetime

from bs4 import BeautifulSoup

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scrapers"))

import pipeline  # noqa: E402
import summary  # noqa: E402
from scrappey_client import (  # noqa: E402
    ScrappeyError,
    fetch,
    get_call_count,
    reset_call_count,
)

MAX_VISITS = 5
SIGMA_THRESHOLD = 2.0
MIN_GROUP_SIZE = 3

# Polish + English red-flag keywords. Prefixes chosen so Polish inflections
# match (e.g. "uszkodzony", "uszkodzona" both hit "uszkodzon").
RED_FLAGS = [
    "uszkodzon", "niesprawny", "niesprawna", "nie włącza", "nie włacza",
    "nie dziala", "nie działa", "bez matrycy", "bez ekranu", "bez wyświetlacza",
    "bez wyswietlacza", "parts only", "na części", "na czesci", "na czesci zamienne",
    "icloud lock", "icloud locked", "blokada icloud", "blokada aktywacji",
    "stan nieznany", "water damage", "zalany", "zalana", "zalane",
    "stłuczon", "stluczon", "pęknięt", "pekniet", "pęknięty ekran",
    "uszkodzona matryca", "wymiany", "do renowacji", "do naprawy",
]


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def cpu_class(cpu):
    """Group M1/M1 Pro/M1 Max into a single 'M1' bucket for outlier stats."""
    if not cpu:
        return ""
    m = re.match(r"M(\d+)", cpu.upper())
    return f"M{m.group(1)}" if m else cpu.upper()


def toks_per_kpln(deal):
    price = deal.get("priceNum")
    tg = deal.get("llama2_7b_q4_tg")
    if not price or not tg:
        return None
    return (tg / price) * 1000


def find_outliers(db):
    """Return list of candidate deals whose toksPerKPLN > mean + Nσ per CPU class."""
    candidates = []
    groups = {}
    for d in db:
        if d.get("hidden") or d.get("broken") or d.get("expired"):
            continue
        if not d.get("url"):
            continue
        ratio = toks_per_kpln(d)
        if ratio is None:
            continue
        klass = cpu_class(d.get("cpu", ""))
        if not klass:
            continue
        groups.setdefault(klass, []).append((ratio, d))

    for klass, items in groups.items():
        if len(items) < MIN_GROUP_SIZE:
            continue
        ratios = [r for r, _ in items]
        mean = sum(ratios) / len(ratios)
        variance = sum((r - mean) ** 2 for r in ratios) / len(ratios)
        sigma = math.sqrt(variance)
        if sigma == 0:
            continue
        threshold = mean + SIGMA_THRESHOLD * sigma
        for ratio, deal in items:
            if ratio > threshold:
                candidates.append({
                    "deal": deal,
                    "ratio": ratio,
                    "group": klass,
                    "group_mean": mean,
                    "group_sigma": sigma,
                    "threshold": threshold,
                })
    candidates.sort(key=lambda c: c["ratio"], reverse=True)
    return candidates


def scan_page_text(page_text):
    text = (page_text or "").lower()
    for kw in RED_FLAGS:
        if kw in text:
            return kw
    return None


def fetch_html_text(url, timeout=180):
    """Fetch rendered HTML via Scrappey, return (title+visible_text, blocked)."""
    html = fetch(url, timeout=timeout)
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    combined = f"{title}\n{text}"
    blocked = (
        "captcha-delivery" in html.lower()
        or bool(re.search(r"Potwierd.+cz.owiekiem", combined, re.I))
    )
    return combined, blocked


def _section(
    candidates_count=0,
    visited=0,
    auto_hidden=0,
    hides=None,
    blocked=False,
    skipped=None,
    scrappey_calls=0,
    scrappey_error=None,
):
    section = {
        "candidates": candidates_count,
        "visited": visited,
        "auto_hidden": auto_hidden,
        "hides": hides or [],
        "blocked": blocked,
        "skipped": skipped or "",
        "scrappey_calls": scrappey_calls,
        "sigma_threshold": SIGMA_THRESHOLD,
        "max_visits": MAX_VISITS,
    }
    if scrappey_error:
        section["scrappey_error"] = scrappey_error
    return section


def main():
    dry_run = "--dry-run" in sys.argv[1:]

    if not dry_run:
        summary.clear_section_actions("outliers")

    db = pipeline.load_db()
    candidates = find_outliers(db)
    if not candidates:
        log("[outliers] no candidates this run")
        if not dry_run:
            summary.write_section("outliers", _section())
        return 0

    if dry_run:
        log(f"[outliers] dry run — {len(candidates)} candidate(s) above {SIGMA_THRESHOLD}σ:")
        for c in candidates:
            d = c["deal"]
            log(
                f"  {c['group']} ratio={c['ratio']:.1f} (thr={c['threshold']:.1f}) "
                f"price={d.get('price','?')} {d.get('cpu','?')}/{d.get('ram','?')}/{d.get('disk','?')} "
                f"→ {d.get('url','?')}"
            )
        return 0

    log(f"[outliers] {len(candidates)} candidate(s) above {SIGMA_THRESHOLD}σ; visiting up to {MAX_VISITS} via Scrappey")

    reset_call_count()
    hides = []
    visited = 0
    blocked_flag = False
    scrappey_err: str | None = None
    today = datetime.now().strftime("%Y-%m-%d")

    for i, cand in enumerate(candidates[:MAX_VISITS]):
        deal = cand["deal"]
        url = deal["url"]
        log(
            f"[outliers] {i+1}/{min(len(candidates), MAX_VISITS)} "
            f"group={cand['group']} ratio={cand['ratio']:.1f} "
            f"(mean={cand['group_mean']:.1f} σ={cand['group_sigma']:.1f}) url={url}"
        )
        try:
            text, blocked = fetch_html_text(url)
        except ScrappeyError as exc:
            log(f"[outliers] Scrappey failed: {exc}")
            scrappey_err = str(exc)
            blocked_flag = True
            break
        except Exception as exc:  # noqa: BLE001
            log(f"[outliers] visit failed: {exc}")
            continue
        if blocked:
            log("[outliers] upstream block persisted through Scrappey — aborting")
            blocked_flag = True
            break
        visited += 1
        kw = scan_page_text(text)
        if kw:
            reason = f"auto-outlier: {kw}"
            deal["hidden"] = True
            deal["hidden_at"] = today
            deal["hidden_reason"] = reason
            pipeline.add_hidden_fp(url, pipeline.make_listing_fp(deal), reason=reason)
            hides.append({
                "url": url,
                "keyword": kw,
                "group": cand["group"],
                "ratio": round(cand["ratio"], 1),
                "title": (deal.get("title") or "")[:120],
            })
            log(f"[outliers] HIDE: matched '{kw}' — {deal.get('title','')[:80]}")
        else:
            log(f"[outliers] clean: no red-flag keywords matched — {deal.get('title','')[:80]}")
        if i + 1 < min(len(candidates), MAX_VISITS):
            time.sleep(random.uniform(0.5, 1.5))

    if hides:
        pipeline.save_db(db)
        log(f"[outliers] auto-hid {len(hides)} listing(s); db saved")
    else:
        log("[outliers] no listings auto-hidden")

    summary.write_section("outliers", _section(
        candidates_count=len(candidates),
        visited=visited,
        auto_hidden=len(hides),
        hides=hides,
        blocked=blocked_flag,
        scrappey_calls=get_call_count(),
        scrappey_error=scrappey_err,
    ))
    if blocked_flag:
        summary.append_action_required(
            "outlier visits failed via Scrappey — check .scrappey-key balance + service status",
            section="outliers",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
