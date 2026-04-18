#!/usr/bin/env python3
"""
Thin Scrappey API wrapper. Scrappey solves DataDome and returns rendered HTML.

Usage:
    from scrappey_client import fetch, ScrappeyError
    html = fetch("https://allegro.pl/...")
    html2 = fetch("https://allegro.pl/...?p=2", session_id=<uuid>)

API key is read from .scrappey-key (repo root) or SCRAPPEY_KEY env var.
Billing: €0.001 per full-browser request (approx $0.00108).

Retries: transient failures (transport, unverified solution, 5xx) retry with
2s / 8s / 32s backoff. Permanent failures (401 auth, 402 quota, 403 API) bail
immediately. `_call_count` is thread-safe and counted once per user-initiated
fetch (not once per HTTP attempt).
"""
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.request
import uuid

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY_FILE = REPO_ROOT / ".scrappey-key"
ENDPOINT = "https://publisher.scrappey.com/api/v1"

_call_count = 0
_call_count_lock = threading.Lock()

_RETRY_WAITS = (2, 8)  # seconds between attempts; 3 attempts total including first
_PERMANENT_ERROR_MARKERS = ("HTTP 401", "HTTP 402")  # auth/quota — never retry these
# Scrappey signals "my proxy got banned by DataDome, try again" via CODE-0010.
# Retrying rotates the proxy; when Scrappey's whole pool is flagged this still
# fails, but 3 attempts cap the wall time at ~2 min and the safety gate then
# records the host as "incomplete" so mark_stale skips its listings.
_SCRAPPEY_PROXY_BAN_MARKER = "CODE-0010"


class ScrappeyError(RuntimeError):
    """Raised when Scrappey cannot return a verified response."""


def get_call_count() -> int:
    return _call_count


def reset_call_count() -> None:
    global _call_count
    with _call_count_lock:
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


def _post_once(body: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        f"{ENDPOINT}?key={_load_key()}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise ScrappeyError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8','replace')}") from e
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise ScrappeyError(f"transport error: {e}") from e

    # Scrappey returns 200 at the HTTP layer even when its internal flow
    # failed. Surface the diagnostic `error` field so retries and logs can
    # distinguish "proxy got banned, try again" from transport issues.
    err = payload.get("error")
    if err:
        raise ScrappeyError(f"scrappey: {err}")
    return payload


def _post(body: dict, timeout: int) -> dict:
    """POST with retry on transient errors. Counts once per user-initiated call.

    When Scrappey returns CODE-0010 (proxy banned by DataDome), we rotate the
    `session` on the next attempt so Scrappey draws a fresh proxy from its
    pool — otherwise retries would keep hitting the same banned IP.
    """
    global _call_count
    with _call_count_lock:
        _call_count += 1

    current = dict(body)  # copy so we can mutate session without affecting caller
    last_err: ScrappeyError | None = None
    for attempt, wait in enumerate((0,) + _RETRY_WAITS):
        if wait:
            time.sleep(wait)
        try:
            return _post_once(current, timeout)
        except ScrappeyError as e:
            err = str(e)
            if any(marker in err for marker in _PERMANENT_ERROR_MARKERS):
                raise  # auth/quota — don't retry
            last_err = e
            # Rotate session on proxy-ban so the retry draws a new proxy.
            if _SCRAPPEY_PROXY_BAN_MARKER in err and "session" in current:
                current["session"] = str(uuid.uuid4())
    assert last_err is not None
    raise last_err


def fetch(url: str, timeout: int = 90, datadome: bool = True, session_id: str | None = None) -> str:
    """POST to Scrappey, return rendered HTML string.

    Raises ScrappeyError on transport failure, non-200 response, or unverified
    solution (the page was not actually loaded past the anti-bot wall).

    When `session_id` is provided, Scrappey reuses the same browser session
    across calls — cookies / DataDome solutions cached, subsequent pages of
    the same search complete in ~3-5s instead of ~15-30s.
    """
    body = {"cmd": "request.get", "url": url}
    if datadome:
        body["datadome"] = True
    if session_id:
        body["session"] = session_id
    payload = _post(body, timeout)

    sol = payload.get("solution") or {}
    if not sol.get("verified"):
        raise ScrappeyError(f"unverified solution (status={sol.get('statusCode')})")
    if sol.get("statusCode") not in (200, 201, 304):
        raise ScrappeyError(f"upstream HTTP {sol.get('statusCode')}")

    html = sol.get("response")
    if not isinstance(html, str) or not html:
        raise ScrappeyError("empty response body")
    return html


def fetch_status(url: str, timeout: int = 90, datadome: bool = True, session_id: str | None = None) -> int | None:
    """POST to Scrappey, return upstream status code (or None if no solution).

    Unlike fetch(), this does NOT raise on 4xx/5xx or on verified=False — the
    whole point is to read the upstream status, including 404/410 for expiry
    detection. Only raises ScrappeyError on transport failure.
    """
    body = {"cmd": "request.get", "url": url}
    if datadome:
        body["datadome"] = True
    if session_id:
        body["session"] = session_id
    payload = _post(body, timeout)

    sol = payload.get("solution") or {}
    status = sol.get("statusCode")
    return status if isinstance(status, int) else None
