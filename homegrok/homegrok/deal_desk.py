"""Deal desk: alert settings, price-range forecasts, buy-N-and-sell plans, and saved reports.

Everything here uses REAL data only: the Wholesale Hub's live price history and sources.
Forecasts are statistics over past prices. They describe a likely range, not a guarantee.
"""
import json
import math
import statistics
import time
import urllib.parse
import urllib.request

HUB = "http://127.0.0.1:8800"
DEFAULT_ALERTS = {"muted": False, "min_profit": 2.0, "min_margin": 15.0}


def _hub_json(path, timeout=8):
    try:
        with urllib.request.urlopen(HUB + path, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def alert_settings(ws):
    return {**DEFAULT_ALERTS, **ws.load_config().get("deal_alerts", {})}


def real_opportunities(limit=50, min_profit=0.0):
    rows = _hub_json(f"/api/opportunities?limit={limit}&min_profit={min_profit}") or []
    return [r for r in rows if r.get("is_sample") == 0]   # real rows only


def forecast(points, horizon_days=7):
    """points: [[unix_ts, price], ...]. Returns a likely range for the next horizon_days.

    Uses the middle 80% of past prices (10th to 90th percentile) and the recent trend.
    Confidence depends on how many points and how many days of history there are.
    """
    pts = sorted((t, p) for t, p in points if p and p > 0)
    if len(pts) < 5:
        return {"ok": False, "reason": f"only {len(pts)} price points so far; a forecast needs at least 5"}
    prices = [p for _, p in pts]
    span_days = (pts[-1][0] - pts[0][0]) / 86400 or 0.0001
    # trend: least-squares slope per day over the points, applied to the median
    xs = [(t - pts[0][0]) / 86400 for t, _ in pts]
    mx, my = statistics.mean(xs), statistics.mean(prices)
    var = sum((x - mx) ** 2 for x in xs) or 1e-9
    slope = sum((x - mx) * (p - my) for x, p in zip(xs, prices)) / var
    median = statistics.median(prices)
    lo, hi = sorted(prices)[int(0.1 * (len(prices) - 1))], sorted(prices)[int(0.9 * (len(prices) - 1))]
    expected = median + slope * horizon_days
    spread = max(hi - lo, 0.01)
    if len(pts) >= 60 and span_days >= 30:
        confidence = "good"
    elif len(pts) >= 20 and span_days >= 7:
        confidence = "fair"
    else:
        confidence = "low: few days of history"
    return {"ok": True, "now": round(prices[-1], 2), "median": round(median, 2),
            "range_low": round(max(0.01, expected - spread / 2), 2), "range_high": round(expected + spread / 2, 2),
            "trend_per_day": round(slope, 4), "points": len(pts), "days": round(span_days, 1),
            "confidence": confidence}


def plan(opp, quantity):
    """Buy `quantity` packs at the buy store and sell them at the sell store. Uses the Hub's own
    per-pack profit so fees and shipping stay consistent with the rest of the Hub."""
    quantity = max(1, int(quantity))
    cost_each = float(opp.get("cost", 0))
    profit_each = float(opp.get("profit", 0))
    sell_each = float(opp.get("sell_price", 0))
    return {
        "name": opp.get("name", ""), "brand": opp.get("brand", ""),
        "quantity": quantity,
        "buy_at": opp.get("buy_source", ""), "buy_url": opp.get("buy_url", ""),
        "sell_at": opp.get("sell_source", ""), "sell_url": opp.get("sell_url", ""),
        "buy_each": round(cost_each, 2), "sell_each": round(sell_each, 2),
        "total_cost": round(cost_each * quantity, 2),
        "total_revenue": round(sell_each * quantity, 2),
        "total_profit": round(profit_each * quantity, 2),
        "margin_pct": round(opp.get("margin_pct", 0), 1),
        "caveat": "Profit assumes the sell price holds while you sell all units. Check stock, limits and fees before buying.",
    }


def report(ws, opps, histories):
    """A saved where-to-buy, where-to-sell plan built from real data. Returns (path, markdown)."""
    stamp = time.strftime("%Y-%m-%d %H:%M")
    lines = [f"# Deal plan, {stamp}", "",
             "Built only from real price data in the Wholesale Hub. Forecasts are ranges based on past prices, not guarantees.", ""]
    if not opps:
        lines += ["No real deals in the data yet. Connect a source (eBay keys, or import your own price sheet).", ""]
    for i, o in enumerate(opps[:20], 1):
        fc = histories.get(o.get("product_id"))
        lines += [f"## {i}. {o.get('name', '')} ({o.get('brand', '') or 'no brand'})",
                  f"- **Buy at:** {o.get('buy_source', '')} for ${o.get('cost', 0):.2f} each · {o.get('buy_url', '')}",
                  f"- **Sell at:** {o.get('sell_source', '')} for ${o.get('sell_price', 0):.2f} each · {o.get('sell_url', '')}",
                  f"- **Profit per unit:** ${o.get('profit', 0):.2f} ({o.get('margin_pct', 0):.0f}% margin, after fees and shipping)",
                  f"- **10 units:** cost ${o.get('cost', 0) * 10:.2f}, profit ${o.get('profit', 0) * 10:.2f}"]
        if fc and fc.get("ok"):
            lines.append(f"- **Price forecast next 7 days:** ${fc['range_low']:.2f} to ${fc['range_high']:.2f} "
                         f"(now ${fc['now']:.2f}, {fc['confidence']} confidence from {fc['points']} points)")
        else:
            lines.append("- **Price forecast:** not enough history yet")
        lines.append("")
    lines += ["Before you buy: check the live price, stock and seller on the store page; confirm the sell site's fees and "
              "shipping; keep receipts. HomeGrok never buys or sells for you."]
    folder = ws.root / "reports"
    folder.mkdir(exist_ok=True)
    path = folder / (time.strftime("%Y-%m-%d-%H%M") + ".md")
    text = "\n".join(lines) + "\n"
    path.write_text(text)
    return path, text


SEARCH_SOURCES_CACHE = {"at": 0, "sources": []}


def _sources():
    """Every store the Hub knows, with its own search link pattern (we open links; we don't scrape)."""
    if time.time() - SEARCH_SOURCES_CACHE["at"] > 300:
        data = _hub_json("/api/sources") or {}
        SEARCH_SOURCES_CACHE.update(at=time.time(), sources=data.get("sources", []))
    return SEARCH_SOURCES_CACHE["sources"]


def trace(name, limit_products=5):
    """Where to buy and sell one product, from real data only.

    - search_links: each store's own search page for the name (open them yourself).
    - buy_points:   real offers the Hub holds for matching products, cheapest first.
    - best_pair:    the buy-here, sell-there pair with the highest profit, and the highest margin.
    """
    q = urllib.parse.quote(name.strip())
    search_links = []
    for s in _sources():
        if s.get("search_url") and s.get("enabled", True):
            search_links.append({"store": s["name"], "kind": s.get("kind", ""),
                                 "url": s["search_url"].replace("{q}", q)})
    matches = [p for p in (_hub_json(f"/api/products?q={q}&limit=50") or []) if p.get("is_sample") == 0][:limit_products]
    buy_points, pairs = [], []
    for p in matches:
        detail = _hub_json(f"/api/products/{p['id']}") or {}
        for o in detail.get("offers", []):
            if o.get("is_sample") == 0:
                buy_points.append({"product": p["name"], "brand": p.get("brand", ""), "store": o.get("source_name", o["source"]),
                                   "price": o["price"], "unit_price": o["unit_price"], "pack_qty": o.get("pack_qty"),
                                   "in_stock": bool(o.get("in_stock")), "url": o.get("url", "")})
        for opp in detail.get("opportunities", []):
            if opp.get("is_sample", 0) == 0:
                pairs.append(opp)
    buy_points.sort(key=lambda b: b["unit_price"])
    best_profit = max(pairs, key=lambda r: r["profit"], default=None)
    best_margin = max(pairs, key=lambda r: r["margin_pct"], default=None)
    return {"query": name, "search_links": search_links, "buy_points": buy_points,
            "best_profit": best_profit, "best_margin": best_margin,
            "real_products_found": len(matches)}
