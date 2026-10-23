"""Live deal alerts: watches the Wholesale Hub for new real (non-sample) deals and tells you at once.

Each new deal gets a macOS notification and a card on the dashboard. Only deals from real price
data are shown: the Hub's sample products never reach here.
"""
import json
import subprocess
import threading
import time
import urllib.request

HUB = "http://127.0.0.1:8800/api/alerts?limit=30"
POLL_SECONDS = 60
MIN_PROFIT = 2.0


def _notify(title, body):
    text = body.replace('"', "'")[:200]
    subprocess.run(["osascript", "-e",
                    f'display notification "{text}" with title "{title}" sound name "Glass"'],
                   check=False, capture_output=True)


def _fetch():
    try:
        with urllib.request.urlopen(HUB, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


class DealAlerts:
    def __init__(self, ws):
        self.ws = ws
        self.path = ws.root / "deal_alerts.json"
        self.seen_path = ws.root / "deal_alerts_seen.json"

    def recent(self, n=8):
        return json.loads(self.path.read_text())[-n:][::-1] if self.path.exists() else []

    def _seen(self):
        return set(json.loads(self.seen_path.read_text())) if self.seen_path.exists() else set()

    def check_once(self):
        rows = _fetch()
        if rows is None:
            return 0
        seen = self._seen()
        # only rows explicitly marked real (is_sample == 0) count: anything else is treated as sample
        fresh = [r for r in rows if r["id"] not in seen and r.get("is_sample") == 0]
        if not fresh:
            return 0
        kept = self.recent(50)
        from .deal_desk import alert_settings
        cfg = alert_settings(self.ws)
        for r in sorted(fresh, key=lambda r: r["id"]):
            seen.add(r["id"])
            if r["profit"] < cfg["min_profit"] or r["margin_pct"] < cfg["min_margin"]:
                continue
            item = {"id": r["id"], "time": time.time(), "name": r.get("name", ""), "brand": r.get("brand", ""),
                    "profit": round(r["profit"], 2), "margin_pct": round(r["margin_pct"], 1),
                    "buy_source": r.get("buy_source", ""), "sell_source": r.get("sell_source", "")}
            kept.append(item)
            if cfg["muted"]:   # still recorded on the dashboard, just no Mac notification
                continue
            _notify("Good deal found",
                    f"{item['name']}: buy at {item['buy_source']}, sell at {item['sell_source']}, "
                    f"profit ${item['profit']:.2f} ({item['margin_pct']:.0f}%)")
        self.path.write_text(json.dumps(kept[-200:]))
        self.seen_path.write_text(json.dumps(sorted(seen)[-5000:]))
        return len(fresh)


def start(ws):
    alerts = DealAlerts(ws)

    def loop():
        while True:
            try:
                alerts.check_once()
            except Exception as e:
                print(f"[deal alerts] {e!r}", flush=True)
            time.sleep(POLL_SECONDS)

    threading.Thread(target=loop, daemon=True).start()
    return alerts
