#!/usr/bin/env python3
"""
Reads searches.json and runs the appropriate scraper for each saved search.
Pipes each scraper's output into `pipeline.py add` via a temp file.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SEARCHES = ROOT / "searches.json"
PIPELINE = ROOT / "pipeline.py"

SCRAPERS = {
    "allegro": ROOT / "scrapers" / "allegro.py",
    "olx":     ROOT / "scrapers" / "olx.py",
    "lantre":  ROOT / "scrapers" / "lantre.py",
}


def run_scraper(source: str, entry: dict) -> int:
    """Run scraper for one entry; return count of new deals added (best-effort)."""
    script = SCRAPERS.get(source)
    if not script or not script.exists():
        print(f"[{source}] NO SCRAPER for {entry.get('name')}", file=sys.stderr)
        return 0

    args = ["python3", str(script), entry["url"]]
    if entry.get("used"):
        args.append("--used")
    if entry.get("pages"):
        args.extend(["--pages", str(entry["pages"])])

    print(f"[{source}] scraping: {entry.get('name')}", file=sys.stderr)
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print(f"[{source}] TIMEOUT", file=sys.stderr)
        return 0

    if r.returncode != 0:
        print(f"[{source}] scraper exit {r.returncode}: {r.stderr.strip()[:200]}", file=sys.stderr)
        return 0

    # Scrapers print diagnostics mixed with a final JSON array line on stdout.
    # Find the JSON array.
    json_text = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            json_text = line
            break
    if not json_text:
        print(f"[{source}] no JSON output", file=sys.stderr)
        return 0

    try:
        items = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"[{source}] bad JSON: {e}", file=sys.stderr)
        return 0

    if not items:
        print(f"[{source}] 0 items", file=sys.stderr)
        return 0

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        json.dump(items, tf, ensure_ascii=False)
        tmp = tf.name

    try:
        p = subprocess.run(
            ["python3", str(PIPELINE), "add", tmp],
            capture_output=True, text=True, timeout=120,
        )
        print(p.stdout.strip(), file=sys.stderr)
        if p.returncode != 0:
            print(f"[{source}] pipeline failed: {p.stderr}", file=sys.stderr)
        # Parse 'Added N new' from pipeline output
        for line in p.stdout.splitlines():
            if "Added" in line and "new" in line:
                try:
                    return int(line.split("Added")[1].split("new")[0].strip())
                except (ValueError, IndexError):
                    pass
        return len(items)
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> int:
    data = json.loads(SEARCHES.read_text(encoding="utf-8"))
    total_new = 0
    total_runs = 0
    for source, entries in data.items():
        for entry in entries:
            total_runs += 1
            total_new += run_scraper(source, entry)

    print(json.dumps({"runs": total_runs, "new_deals": total_new}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
