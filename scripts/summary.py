#!/usr/bin/env python3
"""
Shared summary writer for the daily scrape pipeline.

Each step of daily.sh (check_alive, scrape_all, check_outliers, rebuild)
writes a section into .scrape-summary.json via the helpers below.

The file is read-modify-written by the sub-step. Since daily.sh invokes
steps serially there's no concurrency here. server.py exposes the result
via /api/status and index.html renders it.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUMMARY_FILE = REPO / ".scrape-summary.json"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read():
    if not SUMMARY_FILE.exists():
        return {}
    try:
        return json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _write(data):
    SUMMARY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def reset(kind="daily", log_path=""):
    """Call at the start of a run; wipes previous sections."""
    data = {
        "kind": kind,
        "started_at": _now(),
        "finished_at": None,
        "state": "running",
        "alive": None,
        "scrape": None,
        "outliers": None,
        "db_before": None,
        "db_after": None,
        "errors": [],
        "actions_required": [],
        "log_path": log_path or "",
    }
    _write(data)
    return data


def write_section(key, payload):
    data = _read()
    if not data:
        data = reset()
    data[key] = payload
    _write(data)


def merge_section(key, patch):
    data = _read()
    if not data:
        data = reset()
    current = data.get(key) or {}
    if not isinstance(current, dict):
        current = {}
    current.update(patch)
    data[key] = current
    _write(data)


def append_error(msg):
    data = _read() or reset()
    data.setdefault("errors", []).append(str(msg))
    _write(data)


def append_action_required(msg):
    data = _read() or reset()
    actions = data.setdefault("actions_required", [])
    if msg not in actions:
        actions.append(str(msg))
    _write(data)


def set_counts(before=None, after=None):
    data = _read() or reset()
    if before is not None:
        data["db_before"] = before
    if after is not None:
        data["db_after"] = after
    _write(data)


def finalize(state="ok"):
    data = _read() or reset()
    data["finished_at"] = _now()
    data["state"] = state
    try:
        start = datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(data["finished_at"].replace("Z", "+00:00"))
        data["duration_sec"] = int((end - start).total_seconds())
    except (KeyError, ValueError, TypeError):
        pass
    _write(data)


def read():
    return _read()


# ---- CLI wrappers so daily.sh (bash) can invoke these directly ----
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: summary.py {reset|finalize|error|action|count-before|count-after|dump}", file=sys.stderr)
        sys.exit(2)
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "reset":
        reset(kind=(rest[0] if rest else "daily"), log_path=(rest[1] if len(rest) > 1 else ""))
    elif cmd == "finalize":
        finalize(state=(rest[0] if rest else "ok"))
    elif cmd == "error":
        append_error(" ".join(rest))
    elif cmd == "action":
        append_action_required(" ".join(rest))
    elif cmd == "count-before":
        set_counts(before=int(rest[0]))
    elif cmd == "count-after":
        set_counts(after=int(rest[0]))
    elif cmd == "dump":
        print(json.dumps(read(), indent=2))
    else:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        sys.exit(2)
