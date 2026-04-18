"""
Residential-proxy config loader for camoufox-based scrapers.

Reads a single-line proxy URL from `.dataimpulse-proxy` (or `DATAIMPULSE_PROXY`
env var) in the format:
    http://user:pass@host:port

Exposes `load_proxy()` → camoufox/Playwright-shaped dict or None when no
proxy is configured. Callers should treat None as "fall back to Scrappey"
rather than "scrape without a proxy" — DataDome-protected sites need a
residential IP to have any chance of passing.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
PROXY_FILE = REPO_ROOT / ".dataimpulse-proxy"


def load_proxy() -> dict | None:
    """Return {server, username, password} for camoufox/Playwright, or None."""
    raw = os.environ.get("DATAIMPULSE_PROXY")
    if not raw and PROXY_FILE.exists():
        raw = PROXY_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    u = urlparse(raw)
    if not u.hostname or not u.port:
        return None
    return {
        "server": f"{u.scheme}://{u.hostname}:{u.port}",
        "username": u.username or "",
        "password": u.password or "",
    }
