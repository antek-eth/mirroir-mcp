#!/usr/bin/env python3
"""
Reads searches.json and runs the appropriate scraper for each saved search.
Pipes each scraper's output into `pipeline.py add` via a temp file.

Runs up to 3 searches concurrently via ThreadPoolExecutor — Scrappey accepts
parallel requests and the scrapers are CPU-trivial / network-bound, so
parallelism cuts wall time without touching the credit budget.
"""
import json
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summary  # noqa: E402

ROOT = Path(__file__).parent.parent
SEARCHES = ROOT / "searches.json"
PIPELINE = ROOT / "pipeline.py"

SCRAPERS = {
    "allegro":         ROOT / "scrapers" / "allegro.py",
    "allegrolokalnie": ROOT / "scrapers" / "allegrolokalnie.py",
    "olx":             ROOT / "scrapers" / "olx.py",
    "lantre":          ROOT / "scrapers" / "lantre.py",
}

MAX_WORKERS = 3


def run_scraper(source: str, entry: dict):
    """Run scraper for one entry.

    Returns dict: {added:int, items:int, error:str|None, blocked:bool, incomplete:bool}
    """
    script = SCRAPERS.get(source)
    if not script or not script.exists():
        msg = f"no scraper for {entry.get('name')}"
        print(f"[{source}] NO SCRAPER for {entry.get('name')}", file=sys.stderr)
        return {"added": 0, "items": 0, "error": msg, "blocked": False, "incomplete": False}

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
        return {"added": 0, "items": 0, "error": "timeout", "blocked": False, "incomplete": False}

    blocked = "BLOCKED — Scrappey failed" in (r.stderr or "")
    # Exit 4 = incomplete coverage (scraper hit page ceiling with a still-full final page).
    incomplete = r.returncode == 4
    # Exit 4 is NOT a failure — the JSON output is still valid, just partial.
    # Treat like success for parsing, but record incomplete=True so mark_stale
    # safety gate can refuse to expire listings for this host.
    fatal_exit = r.returncode != 0 and not incomplete

    if fatal_exit:
        stderr_tail = (r.stderr or "").strip()[-300:]
        print(f"[{source}] scraper exit {r.returncode}: {stderr_tail[:200]}", file=sys.stderr)
        return {
            "added": 0, "items": 0,
            "error": f"exit {r.returncode}: {stderr_tail[:200]}",
            "blocked": blocked,
            "incomplete": False,
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
        return {"added": 0, "items": 0, "error": "no JSON output", "blocked": blocked, "incomplete": incomplete}

    try:
        items = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"[{source}] bad JSON: {e}", file=sys.stderr)
        return {"added": 0, "items": 0, "error": f"bad JSON: {e}", "blocked": blocked, "incomplete": incomplete}

    if not items:
        print(f"[{source}] 0 items", file=sys.stderr)
        return {"added": 0, "items": 0, "error": None, "blocked": blocked, "incomplete": incomplete}

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
                "incomplete": incomplete,
            }
        added = 0
        for line in p.stdout.splitlines():
            if "Added" in line and "new" in line:
                try:
                    added = int(line.split("Added")[1].split("new")[0].strip())
                    break
                except (ValueError, IndexError):
                    pass
        return {"added": added, "items": len(items), "error": None, "blocked": blocked, "incomplete": incomplete}
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> int:
    summary.clear_section_actions("scrape")
    data = json.loads(SEARCHES.read_text(encoding="utf-8"))

    per_source: dict[str, dict] = {}
    errors: list[dict] = []
    blocked_sources: set[str] = set()
    stats_lock = threading.Lock()

    def job(source: str, entry: dict):
        result = run_scraper(source, entry)
        with stats_lock:
            bucket = per_source.setdefault(source, {
                "runs": 0, "new_deals": 0, "items_seen": 0, "incomplete": False,
            })
            bucket["runs"] += 1
            bucket["new_deals"] += result["added"]
            bucket["items_seen"] += result["items"]
            if result.get("incomplete"):
                bucket["incomplete"] = True
            if result["blocked"]:
                blocked_sources.add(source)
            if result["error"]:
                errors.append({
                    "source": source,
                    "name": entry.get("name", ""),
                    "message": result["error"],
                })
        return result

    futures = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for source, entries in data.items():
            for entry in entries:
                futures.append(pool.submit(job, source, entry))
        for f in as_completed(futures):
            f.result()  # propagate exceptions so we don't silently swallow bugs

    total_runs = sum(b["runs"] for b in per_source.values())
    total_new = sum(b["new_deals"] for b in per_source.values())

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
            f"Scrappey failed for {', '.join(sorted(blocked_sources))} — check .scrappey-key balance + service status",
            section="scrape",
        )
    print(json.dumps({"runs": total_runs, "new_deals": total_new}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
