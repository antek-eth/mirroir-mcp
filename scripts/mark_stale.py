#!/usr/bin/env python3
"""
Mark stale listings as expired based on daily-scrape absence.

The daily scrape bumps `last_seen_in_search` on every URL it finds. This
script runs AFTER the scrape and flips `expired=true, expired_by='search-staleness'`
on any listing that:
  1. is in-scope (matches one of the active searches' filters for its host), and
  2. hasn't been seen in the last GRACE_DAYS scrapes.

It also UN-expires listings that were previously staleness-expired but show up
in today's scrape — self-healing.

Zero Scrappey calls. Runs in sub-second on the full DB.

Default is --dry-run (prints JSON summary, no DB writes). Use --apply to mutate.

Safety gate: if today's .scrape-summary.json shows any host's scrape returned
zero listings, we refuse to expire anything for that host — a bad scrape should
not nuke the DB.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parent.parent
DB_FILE = REPO / "macbook_deals.json"
SEARCHES_FILE = REPO / "searches.json"
SUMMARY_FILE = REPO / ".scrape-summary.json"

# Map the top-level keys in searches.json to the hostname they apply to.
KEY_TO_HOST = {
    "allegro": "allegro.pl",
    "allegrolokalnie": "allegrolokalnie.pl",
    "olx": "www.olx.pl",
    "lantre": "lantre.pl",
    "vinted": "www.vinted.pl",
    "pepper": "www.pepper.pl",
}

DEFAULT_GRACE_DAYS = 7


def _parse_ram_gb(val) -> int | None:
    if not val:
        return None
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else None


def _extract_ram_filters(qs: dict[str, list[str]]) -> set[int]:
    """Pull RAM-size filter values out of allegro/olx search query params."""
    rams: set[int] = set()
    # allegro: wielkosc-pamieci-ram=24 GB
    for v in qs.get("wielkosc-pamieci-ram", []):
        m = re.search(r"(\d+)", v)
        if m:
            rams.add(int(m.group(1)))
    # olx: search[filter_enum_ramsize_laptops][N]=24gb
    for k, vs in qs.items():
        if "ramsize" not in k.lower():
            continue
        for v in vs:
            m = re.search(r"(\d+)", v)
            if m:
                rams.add(int(m.group(1)))
    return rams


def _extract_chip_family(qs: dict[str, list[str]]) -> set[str]:
    """M1/M2/... values from seria-procesora or processorseries params."""
    chips: set[str] = set()
    for k, vs in qs.items():
        if "procesora" not in k.lower() and "processorseries" not in k.lower():
            continue
        for v in vs:
            m = re.search(r"Apple\s*M(\d+)", v, re.I)
            if m:
                chips.add(f"M{m.group(1)}")
                continue
            # Bare "Apple M" (allegro) or "apple-m" (olx) = whole M family
            stripped = v.strip().lower()
            if stripped in {"apple m", "apple-m"}:
                chips |= {"M1", "M2", "M3", "M4", "M5"}
    return chips


def _infer_form_factor(url: str) -> str | None:
    u = url.lower()
    if "/laptopy" in u or "/laptops" in u:
        return "laptop"
    if "/komputery-stacjonarne" in u or "/desktops" in u:
        return "desktop"
    return None


def derive_host_filters(searches: dict) -> dict[str, dict]:
    """Parse searches.json → per-host scope filters.

    Returns {host: {min_ram_gb?, chip_family?, form_factors?}}. Hosts with no
    inferrable filter entry (e.g. lantre: "all Apple refurb") get an empty
    dict, meaning every deal from that host is in-scope.
    """
    out: dict[str, dict] = {}
    for key, host_searches in (searches or {}).items():
        host = KEY_TO_HOST.get(key)
        if not host or not host_searches:
            continue
        merged: dict = {}
        for s in host_searches:
            url = s.get("url", "")
            qs = parse_qs(urlparse(url).query)
            rams = _extract_ram_filters(qs)
            if rams:
                cur = min(rams)
                prev = merged.get("min_ram_gb")
                merged["min_ram_gb"] = cur if prev is None else min(prev, cur)
            chips = _extract_chip_family(qs)
            if chips:
                merged.setdefault("chip_family", set()).update(chips)
            ff = _infer_form_factor(url)
            if ff:
                merged.setdefault("form_factors", set()).add(ff)
        out[host] = merged
    return out


def is_in_scope(deal: dict, host_filter: dict) -> bool:
    """Would this deal appear in one of the host's active searches?"""
    if not host_filter:
        return True  # host has entry but no specific filter → everything in scope
    if "min_ram_gb" in host_filter:
        ram = _parse_ram_gb(deal.get("ram"))
        if ram is None or ram < host_filter["min_ram_gb"]:
            return False
    if "chip_family" in host_filter:
        chip = (deal.get("cpu") or "").split()[0] if deal.get("cpu") else ""
        if chip not in host_filter["chip_family"]:
            return False
    if "form_factors" in host_filter:
        screen = (deal.get("screen") or "").lower()
        model = (deal.get("model") or "").lower()
        ff = "desktop" if screen in {"studio", "mini"} or model in {"studio", "mini"} else "laptop"
        if ff not in host_filter["form_factors"]:
            return False
    return True


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _last_summary_scrape_zeros() -> set[str]:
    """Return hosts whose most recent scrape returned 0 listings (safety gate)."""
    if not SUMMARY_FILE.exists():
        return set()
    try:
        data = json.loads(SUMMARY_FILE.read_text())
    except (ValueError, OSError):
        return set()
    scrape = data.get("scrape")
    if not isinstance(scrape, dict):
        return set()
    per_host = scrape.get("per_host") or scrape.get("per_source") or scrape.get("hosts") or {}
    zero = set()
    unknown_keys: list[str] = []
    for host_key, info in per_host.items():
        if not isinstance(info, dict):
            continue
        # scrape_all.py writes items_seen; older writers may use "count".
        items = info.get("items_seen", info.get("count", -1))
        if items == 0:
            resolved = KEY_TO_HOST.get(host_key)
            if resolved is None:
                # Unknown source key → safety gate would silently fail open
                # for this host. Surface the mapping gap instead.
                unknown_keys.append(host_key)
                continue
            zero.add(resolved)
    if unknown_keys:
        print(
            f"[mark_stale] WARNING: scrape summary has unknown source keys "
            f"{unknown_keys!r}; update KEY_TO_HOST in scripts/mark_stale.py "
            f"or their safety gate will fail open.",
            file=sys.stderr,
        )
    return zero


def mark_stale(
    deals: list[dict],
    host_filters: dict[str, dict],
    grace_days: int,
    today: date,
    zero_scrape_hosts: set[str],
) -> dict:
    today_iso = today.isoformat()
    stale_by_host: Counter[str] = Counter()
    unstale_by_host: Counter[str] = Counter()
    skipped_zero_scrape = 0
    skipped_out_of_scope = 0
    skipped_no_host_filter = 0

    for d in deals:
        url = d.get("url", "")
        if not url:
            continue
        host = _host_of(url)

        # If the scrape for this host returned 0 today, refuse to judge.
        if host in zero_scrape_hosts:
            skipped_zero_scrape += 1
            continue

        # Authoritative HTTP-404-expired records stay as-is.
        if d.get("expired") and d.get("expired_by") not in (None, "", "search-staleness", "unknown"):
            continue

        host_filter = host_filters.get(host)
        if host_filter is None:
            skipped_no_host_filter += 1
            continue

        if not is_in_scope(d, host_filter):
            skipped_out_of_scope += 1
            continue

        last = d.get("last_seen_in_search") or d.get("firstSeen")
        try:
            last_date = datetime.strptime(last, "%Y-%m-%d").date() if last else None
        except (TypeError, ValueError):
            last_date = None

        days_since = (today - last_date).days if last_date else 999

        is_currently_staleness_expired = (
            d.get("expired") and d.get("expired_by") == "search-staleness"
        )

        if is_currently_staleness_expired and last == today_iso:
            # Re-seen today — un-expire.
            d["expired"] = False
            d["expired_at"] = None
            d["expired_by"] = None
            unstale_by_host[host] += 1
        elif not d.get("expired") and days_since > grace_days:
            d["expired"] = True
            d["expired_at"] = today_iso
            d["expired_by"] = "search-staleness"
            stale_by_host[host] += 1

    return {
        "grace_days": grace_days,
        "stale_expired": sum(stale_by_host.values()),
        "stale_unexpired": sum(unstale_by_host.values()),
        "by_host_stale": dict(stale_by_host),
        "by_host_unstale": dict(unstale_by_host),
        "skipped_zero_scrape": skipped_zero_scrape,
        "skipped_out_of_scope": skipped_out_of_scope,
        "skipped_no_host_filter": skipped_no_host_filter,
        "zero_scrape_hosts": sorted(zero_scrape_hosts),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Write DB mutations. Default is --dry-run (preview only).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview only, no DB writes (this is the default; flag is accepted for explicitness).")
    ap.add_argument("--grace-days", type=int,
                    default=int(os.environ.get("CHECK_ALIVE_STALE_GRACE_DAYS", DEFAULT_GRACE_DAYS)),
                    help=f"Days of scrape-absence before a listing is marked stale (default: {DEFAULT_GRACE_DAYS}).")
    args = ap.parse_args()

    db = json.loads(DB_FILE.read_text(encoding="utf-8"))
    searches = json.loads(SEARCHES_FILE.read_text(encoding="utf-8")) if SEARCHES_FILE.exists() else {}
    host_filters = derive_host_filters(searches)
    zero_hosts = _last_summary_scrape_zeros()

    result = mark_stale(db, host_filters, args.grace_days, date.today(), zero_hosts)
    result["dry_run"] = not args.apply
    result["host_filters"] = {
        h: {k: sorted(v) if isinstance(v, set) else v for k, v in f.items()}
        for h, f in host_filters.items()
    }

    if args.apply and (result["stale_expired"] or result["stale_unexpired"]):
        DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

    # Append to summary file if present; otherwise just print.
    if SUMMARY_FILE.exists():
        try:
            summary = json.loads(SUMMARY_FILE.read_text())
        except (ValueError, OSError):
            summary = {}
        summary["stale"] = result
        SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in result.items() if k != "host_filters"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
