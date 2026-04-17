#!/usr/bin/env python3
"""
Check liveness of all non-expired listings.

Stage A (cheap):  plain urllib HEAD, 20-way concurrent.
Stage B (Scrappey): for hosts in SCRAPPEY_ESCALATE_HOSTS that returned 403 or
a transport error in Stage A (Allegro DataDome-blocks bot HEADs), re-check via
Scrappey's full-browser GET. Bounded by CHECK_ALIVE_MAX_ESCALATIONS
(default 50) to cap spend.

Marks listings as expired: true + expired_at: YYYY-MM-DD when
status is 404, 410, or 451 (gone / removed / unavailable for legal reasons).
"""
import json
import os
import sys
import concurrent.futures
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.error

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scrapers"))
import summary  # noqa: E402 — share summary writer across pipeline steps
from scrappey_client import (  # noqa: E402
    ScrappeyError,
    fetch_status,
    get_call_count,
    reset_call_count,
)

DB_FILE = REPO / "macbook_deals.json"
TIMEOUT = 10
WORKERS = 20
EXPIRED_STATUSES = {404, 410, 451}

SCRAPPEY_ESCALATE_HOSTS = {"allegro.pl", "allegrolokalnie.pl"}
MAX_ESCALATIONS = int(os.environ.get("CHECK_ALIVE_MAX_ESCALATIONS", "50"))

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


def _host_matches(url: str, hosts: set[str]) -> bool:
    try:
        h = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(h == domain or h.endswith("." + domain) for domain in hosts)


def _classify(status: int | None) -> str:
    """Return one of: expired, alive, needs_escalation, inconclusive."""
    if status is None:
        return "needs_escalation"
    if status in EXPIRED_STATUSES:
        return "expired"
    if 200 <= status < 400:
        return "alive"
    if status == 403:
        return "needs_escalation"
    return "inconclusive"


def main() -> int:
    summary.clear_section_actions("alive")
    deals = json.loads(DB_FILE.read_text(encoding="utf-8"))
    to_check = [(i, d) for i, d in enumerate(deals) if d.get("url") and not d.get("expired")]

    newly_expired = 0
    errors = 0
    inconclusive = 0
    escalated = 0
    escalated_expired = 0
    escalated_inconclusive = 0
    today = date.today().isoformat()
    expired_samples: list[str] = []
    escalate_queue: list[tuple[int, dict]] = []

    # ---- Stage A: plain HEAD ----
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(head_status, d["url"]): (i, d) for i, d in to_check}
        for fut in concurrent.futures.as_completed(futures):
            i, d = futures[fut]
            status = fut.result()
            verdict = _classify(status)
            if verdict == "expired":
                deals[i]["expired"] = True
                deals[i]["expired_at"] = today
                newly_expired += 1
                if len(expired_samples) < 10:
                    expired_samples.append(d.get("url", ""))
            elif verdict == "alive":
                continue
            elif verdict == "needs_escalation":
                if _host_matches(d["url"], SCRAPPEY_ESCALATE_HOSTS):
                    escalate_queue.append((i, d))
                else:
                    if status is None:
                        errors += 1
                    else:
                        inconclusive += 1
            else:  # inconclusive
                inconclusive += 1

    # ---- Stage B: Scrappey GET for hosts worth the spend ----
    reset_call_count()
    scrappey_err: str | None = None
    consecutive_fails = 0
    CONSECUTIVE_FAIL_LIMIT = 3
    for i, d in escalate_queue[:MAX_ESCALATIONS]:
        try:
            status = fetch_status(d["url"])
            consecutive_fails = 0
        except ScrappeyError as exc:
            scrappey_err = str(exc)
            consecutive_fails += 1
            escalated_inconclusive += 1
            if consecutive_fails >= CONSECUTIVE_FAIL_LIMIT:
                # Key dead or Scrappey down — stop burning requests.
                break
            continue
        escalated += 1
        verdict = _classify(status)
        if verdict == "expired":
            deals[i]["expired"] = True
            deals[i]["expired_at"] = today
            newly_expired += 1
            escalated_expired += 1
            if len(expired_samples) < 10:
                expired_samples.append(d.get("url", ""))
        elif verdict == "alive":
            continue
        else:
            escalated_inconclusive += 1

    skipped_escalations = max(0, len(escalate_queue) - MAX_ESCALATIONS)

    if newly_expired:
        DB_FILE.write_text(
            json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    result = {
        "checked": len(to_check),
        "newly_expired": newly_expired,
        "errors": errors,
        "inconclusive": inconclusive,
        "escalated": escalated,
        "escalated_expired": escalated_expired,
        "escalated_inconclusive": escalated_inconclusive,
        "escalations_queued": len(escalate_queue),
        "escalations_skipped": skipped_escalations,
        "scrappey_calls": get_call_count(),
        "expired_samples": expired_samples,
    }
    if scrappey_err:
        result["scrappey_error"] = scrappey_err
    # Only raise an action if Scrappey gave up on consecutive attempts;
    # a single transient timeout in a long queue isn't worth the alert.
    if scrappey_err and consecutive_fails >= CONSECUTIVE_FAIL_LIMIT:
        summary.append_action_required(
            "check_alive: Scrappey failed repeatedly — check .scrappey-key balance + service status",
            section="alive",
        )
    summary.write_section("alive", result)
    print(json.dumps({k: v for k, v in result.items() if k != "expired_samples"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
