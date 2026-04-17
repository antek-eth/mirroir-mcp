#!/usr/bin/env python3
"""
Lightweight HEAD-based liveness early-confirmation.

Plain urllib HEAD, 20-way concurrent. Only acts on unambiguous "gone" statuses
(404 / 410 / 451). Everything else — 200, 301, 302, 403, 429, 5xx, network
timeouts — is a no-op. Ambiguous statuses are handled by `scripts/mark_stale.py`
via the search-based staleness path.

Refactor note (2026-04-18): the previous Stage B Scrappey escalation was removed
because (a) it cost ~50 credits/day and (b) allegro "removed" pages return HTTP
200 so status-code classification can't distinguish them from live pages. The
search-based path is both cheaper and more accurate.

For on-demand deeper liveness inspection that includes Scrappey-based content
sniffing, see `scripts/check_alive_deep.py` (opt-in, not part of the daily
pipeline).

Marks listings as expired: true, expired_at: YYYY-MM-DD, expired_by: 'http-404'
when status is 404, 410, or 451.
"""
import concurrent.futures
import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import summary  # noqa: E402 — shared summary writer

DB_FILE = REPO / "macbook_deals.json"
TIMEOUT = 10
WORKERS = 20
EXPIRED_STATUSES = {404, 410, 451}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def head_status(url: str) -> int | None:
    """Return HTTP status code for URL; None on network error."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def _classify(status: int | None) -> str:
    """Return one of: expired, alive, needs_escalation, inconclusive.

    `needs_escalation` is unused by this script's default flow, but the helper
    is kept for check_alive_deep.py and for historical compatibility.
    """
    if status is None:
        return "inconclusive"
    if status in EXPIRED_STATUSES:
        return "expired"
    if 200 <= status < 400:
        return "alive"
    if status in (403, 429):
        return "needs_escalation"
    return "inconclusive"


def main() -> int:
    summary.clear_section_actions("alive")
    deals = json.loads(DB_FILE.read_text(encoding="utf-8"))
    to_check = [
        (i, d) for i, d in enumerate(deals)
        if d.get("url") and not d.get("expired")
    ]

    newly_expired = 0
    alive = 0
    inconclusive = 0
    today = date.today().isoformat()
    expired_samples: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(head_status, d["url"]): (i, d) for i, d in to_check}
        for fut in concurrent.futures.as_completed(futures):
            i, d = futures[fut]
            verdict = _classify(fut.result())
            if verdict == "expired":
                deals[i]["expired"] = True
                deals[i]["expired_at"] = today
                deals[i]["expired_by"] = "http-404"
                newly_expired += 1
                if len(expired_samples) < 10:
                    expired_samples.append(d.get("url", ""))
            elif verdict == "alive":
                alive += 1
            else:
                inconclusive += 1

    if newly_expired:
        DB_FILE.write_text(
            json.dumps(deals, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    result = {
        "checked": len(to_check),
        "newly_expired": newly_expired,
        "alive": alive,
        "inconclusive": inconclusive,
        "expired_samples": expired_samples,
    }
    summary.write_section("alive", result)
    print(json.dumps({k: v for k, v in result.items() if k != "expired_samples"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
