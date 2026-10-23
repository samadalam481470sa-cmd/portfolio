"""Self-check: runs HomeGrok's tests and reports every failure. It never edits code.

Each check is independent, so one failure can't hide another. Results go to
workspace/logs/selfcheck.json and show on the dashboard. Fixes are made by a person
(or by a reviewed change), never automatically.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _check(name, fn, results):
    try:
        detail = fn()
        results.append({"name": name, "ok": True, "detail": detail or ""})
    except Exception as e:
        results.append({"name": name, "ok": False, "detail": f"{type(e).__name__}: {str(e)[:300]}"})


def _relearn():
    out = subprocess.run([sys.executable, "-m", "homegrok.relearn", "--selftest"], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0 and "selftest ok" in out.stdout, (out.stderr or out.stdout)[-300:]
    return "continual-learning library self-test"


def _fact_checks():
    from .apply import check_fact, guard, answers
    from .config import Workspace
    a = answers(Workspace())   # the same merged settings the filler uses
    assert check_fact("What is your GPA?", "3.2", a) == str(a.get("gpa"))
    assert check_fact("Zip code", "75001", a) == str(a.get("zip"))
    assert guard("Have you ever been convicted of a felony?", "Yes") == "YOUR_ANSWER"
    assert guard("Are you legally authorized to work in the US?", "No") == "YOUR_ANSWER"
    return "fact guards and checks"


def _answers():
    from .apply import answer_for, profile_from_resume, answers
    from .profile import current_resume
    from .config import Workspace
    ws = Workspace()
    p, a = profile_from_resume(current_resume(ws)), answers(ws)
    f = lambda q: answer_for({"question": q, "own": "", "label": q, "options": []}, p, a)
    assert f("Do you now or in the future require visa sponsorship?") == "YOUR_ANSWER"
    assert f("Are you a U.S. citizen?") == "YOUR_ANSWER"
    assert f("What is your expected salary?") == "YOUR_SALARY"
    return "saved answers"


def _matching():
    from .apply import same_answer, search_terms
    assert same_answer("Example University - City", "The Example University at City")
    assert not same_answer("University of City", "The Example University at City")
    assert search_terms("City")[0] == "City"
    return "option matching"


def _knowledge():
    from .config import Workspace
    from .knowledge import search
    search(Workspace(), "test question", k=3)
    return "unified knowledge search runs"


def _deals():
    from .deal_desk import forecast, plan
    day = 86400
    flat = forecast([[1_700_000_000 + i * day, 10.0] for i in range(40)])
    assert flat["ok"] and abs(flat["median"] - 10.0) < 1e-6
    p = plan({"name": "x", "cost": 4.0, "sell_price": 7.5, "profit": 2.75, "margin_pct": 30}, 10)
    assert abs(p["total_profit"] - 27.5) < 1e-6
    return "forecast and plan math"


def _jobs():
    from .config import Workspace
    from .jobs import JobScout
    JobScout(Workspace()).confirmed_open(5)
    return "job database"


def _http(url, key=None):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def _services():
    from .config import Workspace
    assert _http("http://127.0.0.1:8000/api/health") == 200, "HomeGrok web server"
    key = Workspace().api_key.read_text().strip()
    assert _http("http://127.0.0.1:8000/api/status", key) == 200, "authorized status"
    assert _http("http://127.0.0.1:8800/api/health") == 200, "Wholesale Hub"
    return "web server, status, Hub"


def _disk():
    import shutil
    from .config import Workspace
    free = shutil.disk_usage(Workspace().root).free / 1e9
    assert free > 2, f"only {free:.1f} GB free"
    return f"{free:.0f} GB free"


CHECKS = [("relearn library", _relearn), ("fact checks", _fact_checks), ("saved answers", _answers),
          ("option matching", _matching), ("knowledge search", _knowledge), ("deal math", _deals),
          ("job database", _jobs), ("services", _services), ("disk space", _disk)]


def run(ws):
    results = []
    for name, fn in CHECKS:
        _check(name, fn, results)
    report = {"time": time.time(), "passed": sum(r["ok"] for r in results), "total": len(results), "results": results}
    (ws.logs / "selfcheck.json").write_text(json.dumps(report, indent=1))
    failed = [r for r in results if not r["ok"]]
    if failed:
        with open(ws.logs / "activity.jsonl", "a") as f:
            for r in failed:
                f.write(json.dumps({"time": time.time(), "message": f"Self-check FAILED: {r['name']}: {r['detail']}"}) + "\n")
    return report


if __name__ == "__main__":
    from .config import Workspace
    rep = run(Workspace())
    for r in rep["results"]:
        print(("PASS " if r["ok"] else "FAIL ") + r["name"] + (f" - {r['detail']}" if r["detail"] else ""))
    print(f"{rep['passed']}/{rep['total']} checks passed")
