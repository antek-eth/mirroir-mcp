#!/usr/bin/env python3
"""
Check liveness of all non-expired listings via HTTP HEAD.

Marks listings as expired: true + expired_at: YYYY-MM-DD when
status is 404, 410, or 451 (gone / removed / unavailable for legal reasons).

Logs summary only — no per-URL noise. Takes ~30s for 600 URLs.
Non-2xx/3xx that aren't clearly "gone" (e.g. Allegro's 403 bot-block) are
counted as inconclusive and the listing is left unchanged.
"""
import json
import sys
import concurrent.futures
from datetime import date
from pathlib import Path
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summary  # noqa: E402 — share summary writer across pipeline steps

DB_FILE = Path(__file__).parent.parent / "macbook_deals.json"
TIMEOUT = 10
WORKERS = 20
EXPIRED_STATUSES = {404, 410, 451}

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


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


def main() -> int:
    deals = json.loads(DB_FILE.read_text(encoding="utf-8"))
    to_check = [(i, d) for i, d in enumerate(deals) if d.get("url") and not d.get("expired")]

    newly_expired = 0
    errors = 0
    inconclusive = 0
    today = date.today().isoformat()
    expired_samples = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(head_status, d["url"]): (i, d) for i, d in to_check}
        for fut in concurrent.futures.as_completed(futures):
            i, d = futures[fut]
            status = fut.result()
            if status is None:
                errors += 1
            elif status in EXPIRED_STATUSES:
                deals[i]["expired"] = True
                deals[i]["expired_at"] = today
                newly_expired += 1
                if len(expired_samples) < 10:
                    expired_samples.append(d.get("url", ""))
            elif status >= 400:
                inconclusive += 1

    if newly_expired:
        DB_FILE.write_text(
            json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    result = {
        "checked": len(to_check),
        "newly_expired": newly_expired,
        "errors": errors,
        "inconclusive": inconclusive,
        "expired_samples": expired_samples,
    }
    summary.write_section("alive", result)
    print(json.dumps({k: v for k, v in result.items() if k != "expired_samples"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
