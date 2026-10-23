"""End-to-end check. Starts a private copy of the hub, tests it, and stops it.

Run from the project folder:   python3 tests/smoke_test.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    tmp = tempfile.mkdtemp()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, HUB_PORT=str(port), HUB_DATA_DIR=f"{tmp}/data",
               HUB_IMPORT_DIR=f"{tmp}/imports", HUB_PRODUCTS="120")
    proc = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures = []

    def get(path):
        return json.load(urllib.request.urlopen(base + path, timeout=10))

    def check(name, ok, detail=""):
        print(("PASS  " if ok else "FAIL  ") + name + (f"  {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    try:
        for _ in range(60):
            try:
                if get("/api/overview")["products"] >= 120:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        time.sleep(11)  # let the score loop run once

        o = get("/api/overview")
        check("120 sample products loaded", o["products"] == 120, str(o["products"]))
        check("sample mode flag is on", o["sample_mode"] is True)
        check("live updates are flowing", o["total_updates"] > 456, str(o["total_updates"]))

        deals = get("/api/opportunities?limit=5")
        check("opportunities exist", len(deals) > 0)
        d = deals[0]
        math_ok = abs(d["profit"] - (d["sell_price"] - d["fees"] - d["ship"] - d["cost"])) < 0.01
        check("profit equals price - fees - shipping - cost", math_ok)
        check("buy and sell links present", bool(d["buy_url"]) and bool(d["sell_url"]))
        check("trending has rows", len(get("/api/trending?limit=5")) > 0)
        check("popular has rows", len(get("/api/popular?limit=5")) > 0)
        check("searched has rows", len(get("/api/searched?limit=5")) > 0)
        check("cheapest has rows", len(get("/api/cheapest?limit=5")) > 0)

        pid = d["product_id"]
        detail = get(f"/api/products/{pid}")
        check("product detail has offers", len(detail["offers"]) > 0)
        hist = get(f"/api/products/{pid}/history?source={detail['offers'][0]['source']}&hours=24")
        check("price history has points", len(hist) > 1, str(len(hist)))

        csv_text = ("source,name,brand,category,upc,product_key,pack_qty,price,url,in_stock\n"
                    "samsclub,Smoke Item,SmokeBrand,Test,,smoke-1,100,10.00,https://example.com/a,1\n"
                    "ebay,Smoke Item,SmokeBrand,Test,,smoke-1,100,40.00,https://example.com/b,1\n"
                    "nowhere,Bad,Bad,Test,,bad,1,1,,1\n")
        req = urllib.request.Request(base + "/api/import/csv", data=csv_text.encode(), method="POST")
        res = json.load(urllib.request.urlopen(req, timeout=10))
        check("csv import saved 2 rows and skipped 1", res["imported"] == 2 and res["bad_rows"] == 1)
        smoke = get("/api/opportunities?q=Smoke%20Item")
        # cost 10.00, fees 40 x 13.5% = 5.40, shipping 4.00, profit 20.60
        check("imported pair gives the expected profit",
              len(smoke) == 1 and abs(smoke[0]["profit"] - 20.60) < 0.01,
              str(smoke[0]["profit"] if smoke else None))

        urllib.request.urlopen(urllib.request.Request(
            base + "/api/sources/ebay", data=json.dumps({"fee_pct": 50}).encode(),
            headers={"Content-Type": "application/json"}, method="POST"), timeout=20)
        smoke = get("/api/opportunities?q=Smoke%20Item")
        check("changing a fee updates profit at once",
              len(smoke) == 1 and abs(smoke[0]["profit"] - 6.00) < 0.01,
              str(smoke[0]["profit"] if smoke else None))

        with urllib.request.urlopen(base + "/api/stream", timeout=10) as stream:
            line = b""
            t0 = time.time()
            while b"data:" not in line and time.time() - t0 < 5:
                line = stream.readline()
            check("live stream sends events", b"data:" in line)

        page = urllib.request.urlopen(base + "/", timeout=10).read().decode()
        check("dashboard page is served", "Wholesale Hub" in page)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    print("All checks passed." if not failures else f"{len(failures)} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
