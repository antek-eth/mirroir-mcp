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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summary  # noqa: E402

ROOT = Path(__file__).parent.parent
SEARCHES = ROOT / "searches.json"
PIPELINE = ROOT / "pipeline.py"

SCRAPERS = {
    "allegro": ROOT / "scrapers" / "allegro.py",
    "olx":     ROOT / "scrapers" / "olx.py",
    "lantre":  ROOT / "scrapers" / "lantre.py",
}


def run_scraper(source: str, entry: dict):
    """Run scraper for one entry.

    Returns dict: {added:int, items:int, error:str|None, blocked:bool}
    """
    script = SCRAPERS.get(source)
    if not script or not script.exists():
        msg = f"no scraper for {entry.get('name')}"
        print(f"[{source}] NO SCRAPER for {entry.get('name')}", file=sys.stderr)
        return {"added": 0, "items": 0, "error": msg, "blocked": False}

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
        return {"added": 0, "items": 0, "error": "timeout", "blocked": False}

    blocked = "BLOCKED — Scrappey failed" in (r.stderr or "")
    if r.returncode != 0:
        stderr_tail = (r.stderr or "").strip()[-300:]
        print(f"[{source}] scraper exit {r.returncode}: {stderr_tail[:200]}", file=sys.stderr)
        return {
            "added": 0, "items": 0,
            "error": f"exit {r.returncode}: {stderr_tail[:200]}",
            "blocked": blocked,
        }

    # Scrapers print diagnostics mixed with a final JSON array line on stdout.
    json_text = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            json_text = line
            break
    if not json_text:
        print(f"[{source}] no JSON output", file=sys.stderr)
        return {"added": 0, "items": 0, "error": "no JSON output", "blocked": blocked}

    try:
        items = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"[{source}] bad JSON: {e}", file=sys.stderr)
        return {"added": 0, "items": 0, "error": f"bad JSON: {e}", "blocked": blocked}

    if not items:
        print(f"[{source}] 0 items", file=sys.stderr)
        return {"added": 0, "items": 0, "error": None, "blocked": blocked}

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
            return {
                "added": 0, "items": len(items),
                "error": f"pipeline exit {p.returncode}",
                "blocked": blocked,
            }
        added = 0
        for line in p.stdout.splitlines():
            if "Added" in line and "new" in line:
                try:
                    added = int(line.split("Added")[1].split("new")[0].strip())
                    break
                except (ValueError, IndexError):
                    pass
        return {"added": added, "items": len(items), "error": None, "blocked": blocked}
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> int:
    data = json.loads(SEARCHES.read_text(encoding="utf-8"))
    total_new = 0
    total_runs = 0
    per_source = {}
    errors = []
    blocked_sources = set()

    for source, entries in data.items():
        per_source.setdefault(source, {"runs": 0, "new_deals": 0, "items_seen": 0})
        for entry in entries:
            total_runs += 1
            per_source[source]["runs"] += 1
            result = run_scraper(source, entry)
            per_source[source]["new_deals"] += result["added"]
            per_source[source]["items_seen"] += result["items"]
            total_new += result["added"]
            if result["blocked"]:
                blocked_sources.add(source)
            if result["error"]:
                errors.append({
                    "source": source,
                    "name": entry.get("name", ""),
                    "message": result["error"],
                })

    section = {
        "runs": total_runs,
        "new_deals": total_new,
        "per_source": per_source,
        "errors": errors,
        "blocked_sources": sorted(blocked_sources),
    }
    summary.write_section("scrape", section)
    if blocked_sources:
        summary.append_action_required(
            f"Scrappey failed for {', '.join(sorted(blocked_sources))} — check .scrappey-key balance + service status"
        )
    print(json.dumps({"runs": total_runs, "new_deals": total_new}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
