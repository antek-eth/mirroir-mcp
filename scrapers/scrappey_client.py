#!/usr/bin/env python3
"""
Thin Scrappey API wrapper. Scrappey solves DataDome and returns rendered HTML.

Usage:
    from scrappey_client import fetch, ScrappeyError
    html = fetch("https://allegro.pl/...")

API key is read from .scrappey-key (repo root) or SCRAPPEY_KEY env var.
Billing: €0.001 per full-browser request (approx $0.00108).
"""
import json
import os
import pathlib
import urllib.request
import urllib.error

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY_FILE = REPO_ROOT / ".scrappey-key"
ENDPOINT = "https://publisher.scrappey.com/api/v1"

_call_count = 0


class ScrappeyError(RuntimeError):
    """Raised when Scrappey cannot return a verified response."""


def get_call_count() -> int:
    return _call_count


def reset_call_count() -> None:
    global _call_count
    _call_count = 0


def _load_key() -> str:
    key = os.environ.get("SCRAPPEY_KEY")
    if key:
        return key.strip()
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    raise ScrappeyError(
        f"no Scrappey API key (set SCRAPPEY_KEY env or create {KEY_FILE})"
    )


def _post(body: dict, timeout: int) -> dict:
    global _call_count
    req = urllib.request.Request(
        f"{ENDPOINT}?key={_load_key()}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    _call_count += 1
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise ScrappeyError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8','replace')}") from e
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise ScrappeyError(f"transport error: {e}") from e


def fetch(url: str, timeout: int = 180, datadome: bool = True) -> str:
    """POST to Scrappey, return rendered HTML string.

    Raises ScrappeyError on transport failure, non-200 response, or unverified
    solution (the page was not actually loaded past the anti-bot wall).
    """
    body = {"cmd": "request.get", "url": url}
    if datadome:
        body["datadome"] = True
    payload = _post(body, timeout)

    sol = payload.get("solution") or {}
    if not sol.get("verified"):
        raise ScrappeyError(f"unverified solution (status={sol.get('statusCode')})")
    if sol.get("statusCode") not in (200, 201, 304):
        raise ScrappeyError(f"upstream HTTP {sol.get('statusCode')}")

    html = sol.get("response")
    if not isinstance(html, str) or len(html) < 1000:
        raise ScrappeyError("empty or truncated response body")
    return html


def fetch_status(url: str, timeout: int = 120, datadome: bool = True) -> int | None:
    """POST to Scrappey, return upstream status code (or None if no solution).

    Unlike fetch(), this does NOT raise on 4xx/5xx or on verified=False — the
    whole point is to read the upstream status, including 404/410 for expiry
    detection. Only raises ScrappeyError on transport failure.
    """
    body = {"cmd": "request.get", "url": url}
    if datadome:
        body["datadome"] = True
    payload = _post(body, timeout)

    sol = payload.get("solution") or {}
    status = sol.get("statusCode")
    return status if isinstance(status, int) else None
