#!/usr/bin/env python3
"""Compute the build identifier for the commit about to be created.

Invoked by .githooks/pre-commit before every commit. Writes version.json
at repo root with the version string and metadata. Stdlib only.

Format: v<YYYY.MM.DD.HHMM>
"""
import json
import pathlib
import subprocess
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "version.json"


def _git(args):
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()
    except Exception:  # noqa: BLE001 — any git failure falls through to defaults
        return ""


def main():
    parent_sha = _git(["rev-parse", "--short=7", "HEAD"]) or "0000000"
    try:
        parent_count = int(_git(["rev-list", "--count", "HEAD"]) or "0")
    except ValueError:
        parent_count = 0
    build = parent_count + 1  # the commit we're about to create
    now = datetime.now()
    version = now.strftime("v%Y.%m.%d.%H%M")
    payload = {
        "version": version,
        "build": build,
        "parent_sha": parent_sha,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(version)


if __name__ == "__main__":
    main()
