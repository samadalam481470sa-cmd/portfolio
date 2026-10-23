"""Watchdog: keeps HomeGrok healthy 24/7. launchd runs it every 2 minutes.

launchd already restarts a service that crashes; the watchdog also catches ones that are still
running but frozen, trims logs so they can't fill the disk, and warns when the disk is nearly full.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

LOG_MAX_BYTES = 5 * 1024 * 1024     # a log bigger than this is trimmed to its newest 1 MB
LOG_KEEP_BYTES = 1024 * 1024
AUTOPILOT_SILENT_MINUTES = 25        # longer than any normal wait or training generation
MIN_FREE_GB = 2


def _responds(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _restart(label):
    subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"], check=False,
                   capture_output=True)


def _trim_logs(ws):
    trimmed = []
    for path in ws.logs.glob("*"):
        if path.is_file() and path.stat().st_size > LOG_MAX_BYTES:
            with open(path, "rb") as f:
                f.seek(-LOG_KEEP_BYTES, os.SEEK_END)
                tail = f.read()
            path.write_bytes(tail[tail.find(b"\n") + 1:])
            trimmed.append(path.name)
    return trimmed


def check(ws, port=8000):
    report = {"time": time.time(), "restarted": [], "problems": []}
    if not _responds(f"http://127.0.0.1:{port}/api/health"):
        _restart("com.homegrok.serve")
        report["restarted"].append("web server (not responding)")
    try:
        status = json.loads((ws.root / "learner.json").read_text())
        silent = time.time() - status.get("updated", 0)
    except (OSError, ValueError):
        silent = float("inf")
    if silent > AUTOPILOT_SILENT_MINUTES * 60:
        _restart("com.homegrok.learn")
        report["restarted"].append(f"autopilot (silent for {int(silent // 60)} min)")
    if (ws.root.parent / "vendor/ollama/ollama").exists() and not _responds("http://127.0.0.1:11434/api/tags", 5):
        _restart("com.homegrok.ollama")
        report["restarted"].append("local model server (not responding)")
    hub = Path.home() / "wholesale-hub"
    if (hub / ".venv/bin/python").exists() and not _responds("http://127.0.0.1:8800/api/health", 10):
        _restart("com.wholesalehub.hub")
        report["restarted"].append("Wholesale Hub (not responding)")
    report["trimmed_logs"] = _trim_logs(ws)
    free_gb = shutil.disk_usage(ws.root).free / 1e9
    report["free_gb"] = round(free_gb, 1)
    if free_gb < MIN_FREE_GB:
        report["problems"].append(f"only {free_gb:.1f} GB free on disk")
    (ws.logs / "watchdog.json").write_text(json.dumps(report))
    if report["restarted"] or report["problems"]:
        with open(ws.logs / "activity.jsonl", "a") as f:
            for item in report["restarted"]:
                f.write(json.dumps({"time": time.time(), "message": f"Watchdog: restarted the {item}"}) + "\n")
            for item in report["problems"]:
                f.write(json.dumps({"time": time.time(), "message": f"Watchdog: {item}"}) + "\n")
    return report
