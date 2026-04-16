#!/usr/bin/env python3
"""
Local control server for the MacBook Deal Explorer.

- Serves `index.html` (and the rest of the repo) on http://127.0.0.1:8000
- POST /api/scrape       → fire scripts/daily.sh (full run + rebuild + commit)
- POST /api/check-alive  → re-check listing liveness + rebuild HTML
- GET  /api/status       → what's running + last daily status + log tail

stdlib only. One job at a time (in-memory lock + on-disk pid file so the
button honestly reflects reality across server restarts).
"""
import argparse
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
STATUS_FILE = ROOT / ".daily-status"
PID_FILE = ROOT / ".server-job.pid"
LOGS = ROOT / "logs"

_lock = threading.Lock()
_job = None  # {"proc": Popen, "kind": str, "started": iso, "log_path": Path}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _start_job(kind: str, cmd: list[str]):
    global _job
    with _lock:
        if _job and _job["proc"].poll() is None:
            return None, f"another job is running: {_job['kind']}"
        # Respect an orphaned pid file from a previous server process.
        orphan = _read_pid_file()
        if orphan and _pid_alive(orphan.get("pid")):
            return None, f"another job is running: {orphan.get('kind')}"

        LOGS.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = LOGS / f"{kind}-{stamp}.log"
        logf = open(log_path, "w", buffering=1)
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _job = {
            "proc": proc,
            "kind": kind,
            "started": _now(),
            "log_path": log_path,
        }
        PID_FILE.write_text(json.dumps({
            "pid": proc.pid,
            "kind": kind,
            "started": _job["started"],
            "log": str(log_path),
        }))
        return _job, None


def _read_pid_file():
    if not PID_FILE.exists():
        return None
    try:
        return json.loads(PID_FILE.read_text())
    except (ValueError, OSError):
        return None


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, ValueError, OSError):
        return False


def _current_running():
    with _lock:
        if _job and _job["proc"].poll() is None:
            return {
                "kind": _job["kind"],
                "started": _job["started"],
                "pid": _job["proc"].pid,
                "log": str(_job["log_path"]),
            }
        # In-memory job done → clear pid file if it's ours.
        if _job and not _pid_alive(_job["proc"].pid):
            PID_FILE.unlink(missing_ok=True)

    orphan = _read_pid_file()
    if orphan and _pid_alive(orphan.get("pid")):
        return orphan
    if orphan:
        PID_FILE.unlink(missing_ok=True)
    return None


def _last_status():
    if not STATUS_FILE.exists():
        return None
    try:
        return json.loads(STATUS_FILE.read_text())
    except ValueError:
        return None


def _tail(path, lines: int = 60) -> str | None:
    try:
        with open(path) as f:
            return "".join(f.readlines()[-lines:])
    except (OSError, TypeError):
        return None


class Handler(SimpleHTTPRequestHandler):
    def _json(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        if self.path in ("/index.html", "/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            running = _current_running()
            tail = _tail(running["log"]) if running and running.get("log") else None
            return self._json(200, {
                "running": running,
                "last": _last_status(),
                "log_tail": tail,
            })
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/scrape":
            _, err = _start_job("scrape", ["bash", str(ROOT / "scripts" / "daily.sh")])
            if err:
                return self._json(409, {"error": err})
            return self._json(202, {"started": True, "kind": "scrape"})
        if self.path == "/api/check-alive":
            _, err = _start_job(
                "check-alive",
                ["bash", "-lc", "python3 scripts/check_alive.py && python3 pipeline.py rebuild"],
            )
            if err:
                return self._json(409, {"error": err})
            return self._json(202, {"started": True, "kind": "check-alive"})
        return self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):  # quiet
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    os.chdir(ROOT)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {ROOT} on http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
