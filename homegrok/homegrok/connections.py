"""Connections: what HomeGrok is plugged into, detected automatically and shown on the page."""
import json
import re
import subprocess
import urllib.parse
import urllib.request
import threading
import time
from pathlib import Path

from .brain import _clean_env, find_cli

REFRESH_SECONDS = 600


def _hub_up():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8800/api/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def hub_deals(query="", limit=8):
    """Best current deals from the Wholesale Hub, read-only. Returns [] if it isn't running."""
    params = urllib.parse.urlencode({"q": query[:80], "limit": limit, "min_profit": 2.0})
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8800/api/opportunities?{params}", timeout=5) as resp:
            rows = json.loads(resp.read())
    except Exception:
        return []
    # made-up sample prices are never passed on as real deals
    return [r for r in rows if not r.get("is_sample")]


class Connections:
    def __init__(self, ws, orch):
        self.ws, self.orch = ws, orch
        self._items, self._checked, self._lock = [], 0.0, threading.Lock()

    def items(self):
        if time.time() - self._checked > REFRESH_SECONDS and self._lock.acquire(blocking=False):
            self._checked = time.time()
            threading.Thread(target=self._refresh, daemon=True).start()   # never slows the page down
        return self._items

    def _connectors(self):
        """Apps connected to your Claude account (Gmail, Google Drive, ...), as Claude Code sees them."""
        cli = find_cli(self.orch.brain.settings.get("cli"))
        if not cli:
            return {}
        try:
            out = subprocess.run([cli, "mcp", "list"], capture_output=True, text=True, timeout=90,
                                 env=_clean_env(cli), cwd=self.orch.brain.sandbox).stdout
        except (OSError, subprocess.SubprocessError):
            return {}
        found = {}
        for line in out.splitlines():
            m = re.match(r"claude\.ai (.+?): \S+ - (✔|✘)", line)
            if m and not m.group(1).startswith("http"):
                found[m.group(1)] = m.group(2) == "✔"
        return found

    def _refresh(self):
        try:
            brain = self.orch.brain.status()
            items = [{"name": "Claude (your subscription)", "ok": brain["enabled"] and brain["cli_found"],
                      "detail": "the brain: chat, research, resumes" + (f" · {brain['model']}" if brain.get("model") else "")}]
            connectors = self._connectors()
            for name in ("Gmail", "Google Calendar", "Google Drive"):
                ok = connectors.pop(name, None)
                items.append({"name": name, "ok": bool(ok),
                              "detail": "connected through your Claude account" if ok else
                                        "not connected · connect it at claude.ai/settings/connectors",
                              "link": None if ok else "https://claude.ai/settings/connectors"})
            for name, ok in connectors.items():
                items.append({"name": name, "ok": ok, "detail": "connected through your Claude account"})
            items.append({"name": "Google Chrome", "ok": Path("/Applications/Google Chrome.app").exists(),
                          "detail": "the window HomeGrok fills applications in"})
            stats = self.orch.scout.stats()
            items.append({"name": "Job sources", "ok": bool(stats["listed"]),
                          "detail": "SimplifyJobs lists + companies' own job boards (Greenhouse, Lever, Ashby, Workday)"})
            items.append({"name": "Mac GPU", "ok": True, "detail": f"local model on {self.orch.server.device}"})
            hub_ok = _hub_up()
            items.append({"name": "Wholesale Hub", "ok": hub_ok,
                          "detail": "deal finder on port 8800 (read-only from here)" if hub_ok else
                                    "not running (start it with ./service.sh install)"})
            self._items = items
        finally:
            self._lock.release()
