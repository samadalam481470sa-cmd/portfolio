"""Serving path: API gateway + monitoring, logging, billing (usage metering), security.

Binds to 127.0.0.1 only. Every API call needs the workspace's API key (as a Bearer token,
or ?key= for the live event stream and file downloads, which browsers can't add headers to).

  GET  /                 the web app
  GET  /api/events       live status pushed to the page (server-sent events)
  GET  /api/status       the same status, once
  GET  /api/history      the saved conversation
  GET  /api/file?path=   a file HomeGrok produced in ~/HomeGrok Results
  POST /api/chat         a message; the reply streams back as JSON lines
  POST /api/reveal       show a result file or folder in Finder
"""
import hashlib
import re
import json
import secrets
import subprocess
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .evolve import load_state
from .learner import read_status
from .orchestrator import Orchestrator
from .tasks import RESULTS_ROOT, describe_schedule, next_run_time
from .apply import apply_dir, opened, retry_urls, skipped_list, submitted_list, read_status as filler_status, save_answer, start as start_filler
from .connections import Connections
from .profile import current_resume_info, set_resume
from .webcorpus import PublicCorpus

PACKAGE = Path(__file__).parent
WEB = PACKAGE / "web" / "index.html"
RATE_LIMIT = 30          # requests
RATE_WINDOW = 60         # seconds
MAX_BODY = 20 * 1024 * 1024
FILLABLE = re.compile(r"greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com")
AUTO_APPLY_MAX_OPEN = 2      # fills two applications at once (as tabs), so the next one starts while another waits
AUTO_APPLY_MAX_WAITING = 5   # at most this many finished applications wait for your Submit click
CONTENT_TYPES = {".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8",
                 ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def code_version():
    """Changes whenever HomeGrok's code changes; open pages reload themselves when it does."""
    h = hashlib.sha1()
    for path in sorted(PACKAGE.rglob("*")):
        if path.suffix in (".py", ".html"):
            h.update(path.read_bytes())
    return h.hexdigest()[:12]


def get_api_key(ws):
    if not ws.api_key.exists():
        ws.api_key.write_text(secrets.token_urlsafe(32))
        ws.api_key.chmod(0o600)
    return ws.api_key.read_text().strip()


def inside_results(path):
    try:
        path = Path(path).resolve()
        path.relative_to(RESULTS_ROOT.resolve())
        return path
    except (ValueError, OSError, RuntimeError):
        return None


class Monitor:
    def __init__(self, ws):
        self.ws = ws
        self.lock = threading.Lock()
        self.requests = self.errors = self.rejected = 0
        self.latencies = deque(maxlen=200)
        usage_path = ws.logs / "usage.json"
        self.usage = json.loads(usage_path.read_text()) if usage_path.exists() else \
            {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}

    def record(self, entry):
        with self.lock:
            self.requests += 1
            if entry.get("error"):
                self.errors += 1
            else:
                self.latencies.append(entry["latency_ms"])
                self.usage["requests"] += 1
                self.usage["prompt_tokens"] += entry["usage"]["prompt_tokens"]
                self.usage["completion_tokens"] += entry["usage"]["completion_tokens"]
                (self.ws.logs / "usage.json").write_text(json.dumps(self.usage))
            with open(self.ws.logs / "requests.jsonl", "a") as f:
                f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **entry}) + "\n")

    def snapshot(self):
        with self.lock:
            lat = sorted(self.latencies)
            return {
                "requests": self.requests, "errors": self.errors, "rate_limited": self.rejected,
                "latency_p50_ms": lat[len(lat) // 2] if lat else None,
                "usage_all_time": dict(self.usage),
            }


def make_handler(ws, orch, monitor, api_key, version, deal_alerts=None):
    hits = defaultdict(deque)
    page = WEB.read_text().replace("__API_KEY__", api_key).replace("__VERSION__", version)
    chat_cache = {"key": None, "count": 0}
    corpus = PublicCorpus(ws)
    connections = Connections(ws, orch)

    def chat_count():
        """How many messages the conversation has; open pages fetch new ones when it grows."""
        try:
            st = orch.chat.path.stat()
        except OSError:
            return 0
        if chat_cache["key"] != (st.st_mtime, st.st_size):
            with open(orch.chat.path, encoding="utf-8") as f:
                chat_cache["count"] = sum(1 for line in f if line.strip())
            chat_cache["key"] = (st.st_mtime, st.st_size)
        return chat_cache["count"]

    jobs_cache = {"time": 0, "data": None}

    def jobs_snapshot():
        if time.time() - jobs_cache["time"] > 20:
            jobs_cache.update(time=time.time(), data={"stats": orch.scout.stats(), "top": orch.scout.confirmed_open(8)})
        return jobs_cache["data"]

    fill_cache = {"time": 0, "jobs": []}

    def fillable_jobs():
        """Confirmed-open jobs on sites HomeGrok can fill without an account, for the dashboard menu."""
        if time.time() - fill_cache["time"] > 30:
            seen = set(opened(ws))
            fill_cache.update(time=time.time(), jobs=[
                {"url": j["url"], "label": f"{j['title']} · {j['company']}", "opened": j["url"] in seen}
                for j in orch.scout.confirmed_open(60) if FILLABLE.search(j["url"])][:25])
        return fill_cache["jobs"]

    def resume_email():
        from .apply import profile_from_resume
        from .profile import current_resume
        return profile_from_resume(current_resume(ws)).get("email", "")

    def snapshot():
        orch.server.maybe_reload()
        orch._maybe_reload_index()
        evo = load_state(ws)
        tasks = []
        for t in reversed(orch.tasks.all()):
            tasks.append({k: t.get(k) for k in ("id", "title", "goal", "status", "steps", "last_run", "next_run",
                                                 "waiting", "folder")}
                         | {"schedule": describe_schedule(t.get("schedule"))}
                         | {"latest": t["log"][-1] if t["log"] else None, "files": t["files"][-6:][::-1],
                            "file_count": len(t["files"])})
        return {
            "version": version,
            "model": orch.server.name, "model_info": orch.server.info, "device": orch.server.device,
            "passages_indexed": len(orch.index.chunks) if orch.index else 0,
            "evolution": {"generation": evo["generation"], "history": evo["history"][-20:]} if evo else None,
            "brain": orch.brain.status(),
            "autopilot": read_status(ws),
            "memory": {"files": len(orch.memory.digests()), "updated": orch.memory.note_updated(),
                       "note": orch.memory.note()},
            "tasks": tasks[:12],
            "deal_settings": __import__("homegrok.deal_desk", fromlist=["x"]).alert_settings(ws),
            "deal_alerts": deal_alerts.recent(8) if deal_alerts else [],
            "jobs": jobs_snapshot(),
            "corpus": corpus.meta(),
            "chat_count": chat_count(),
            "resume": current_resume_info(ws),
            "filler": filler_status(ws),
            "auto_apply": ws.load_config().get("auto_apply", False),
            "auto_submit": ws.load_config().get("auto_submit", False),
            "submitted": submitted_list(ws)[-10:][::-1],
            "apply_email": ws.load_config().get("apply_answers", {}).get("email", ""),
            "resume_email": resume_email(),
            "skipped": skipped_list(ws)[-8:][::-1],
            "fillable": fillable_jobs(),
            "connections": connections.items(),
            "monitor": monitor.snapshot(),
        }

    class Handler(BaseHTTPRequestHandler):
        server_version = "HomeGrok"

        def log_message(self, fmt, *args):
            pass  # structured logging goes through Monitor instead

        def _send(self, code, body, ctype="application/json", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self, query=None):
            supplied = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not supplied and query:
                supplied = query.get("key", [""])[0]
            return secrets.compare_digest(supplied, api_key)

        def _rate_ok(self):
            q = hits[self.client_address[0]]
            now = time.time()
            while q and now - q[0] > RATE_WINDOW:
                q.popleft()
            if len(q) >= RATE_LIMIT:
                monitor.rejected += 1
                return False
            q.append(now)
            return True

        def _read_json(self):
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("request body missing or too large")
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                cookie = dict(c.strip().split("=", 1) for c in self.headers.get("Cookie", "").split(";") if "=" in c)
                if secrets.compare_digest(query.get("k", [""])[0], api_key):
                    self.send_response(303)   # remember this browser, then drop the key from the address bar
                    self.send_header("Set-Cookie", f"hg={api_key}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000")
                    self.send_header("Location", "/")
                    self.end_headers()
                    return
                if not secrets.compare_digest(cookie.get("hg", ""), api_key):
                    return self._send(401, b"<p style='font:16px sans-serif;padding:40px'>HomeGrok is private. Open it "
                                           b"with your link: the HomeGrok icon on your Desktop, or type homegrok in Terminal.</p>",
                                      "text/html; charset=utf-8")
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if url.path == "/api/health":
                return self._send(200, {"ok": True, "model": orch.server.name, "version": version})
            if not self._authorized(query):
                return self._send(401, {"error": "missing or wrong API key"})
            if url.path == "/api/status":
                return self._send(200, snapshot())
            if url.path == "/api/history":
                return self._send(200, {"count": chat_count(), "items": orch.chat.recent(80)})
            if url.path == "/api/events":
                return self._events()
            if url.path == "/api/apply/live":
                live = apply_dir(ws) / "live.jpg"
                if not live.exists():
                    return self._send(404, {"error": "no application open"})
                return self._send(200, live.read_bytes(), "image/jpeg")
            if url.path == "/api/file":
                path = inside_results(query.get("path", [""])[0])
                if not path or not path.is_file():
                    return self._send(404, {"error": "not found"})
                ctype = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
                disposition = "inline" if ctype.startswith("text/") else "attachment"
                return self._send(200, path.read_bytes(), ctype,
                                  {"Content-Disposition": f'{disposition}; filename="{path.name}"'})
            self._send(404, {"error": "not found"})

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last, last_sent = None, 0.0
            try:
                while True:
                    snap = json.dumps(snapshot())
                    if snap != last:
                        self.wfile.write(f"data: {snap}\n\n".encode())
                        self.wfile.flush()
                        last, last_sent = snap, time.time()
                    elif time.time() - last_sent > 15:
                        self.wfile.write(b": still here\n\n")
                        self.wfile.flush()
                        last_sent = time.time()
                    time.sleep(1)
            except OSError:  # the page was closed
                return

        def do_POST(self):
            url = urlparse(self.path)
            if url.path not in ("/api/chat", "/api/reveal", "/api/resume", "/api/apply", "/api/apply/answer",
                                "/api/apply/focus", "/api/bots", "/api/bots/stop", "/api/settings", "/api/deal/plan", "/api/deal/report", "/api/deal/trace"):
                return self._send(404, {"error": "not found"})
            if not self._authorized():
                return self._send(401, {"error": "missing or wrong API key"})
            if not self._rate_ok():
                return self._send(429, {"error": f"rate limit: {RATE_LIMIT} requests per minute"})
            try:
                req = self._read_json()
            except (ValueError, TypeError) as e:
                return self._send(400, {"error": f"bad request: {e}"})
            if url.path == "/api/apply/answer":
                key, answer = str(req.get("key", "")).strip(), str(req.get("answer", "")).strip()
                if not key or not answer:
                    return self._send(400, {"error": "need a question and an answer"})
                save_answer(ws, key, answer)   # the filler uses it within seconds, and on every later application
                return self._send(200, {"ok": True})
            if url.path == "/api/apply/focus":
                (apply_dir(ws) / "focus").write_text(str(req.get("url", "")))
                return self._send(200, {"ok": True})
            if url.path == "/api/deal/plan":
                from .deal_desk import plan
                from .deal_desk import real_opportunities
                wanted = str(req.get("name", "")).lower()
                qty = req.get("quantity", 10)
                match = next((o for o in real_opportunities(200) if wanted and wanted in o.get("name", "").lower()), None)
                if not match:
                    return self._send(404, {"error": "no real deal with that name right now"})
                return self._send(200, plan(match, qty))
            if url.path == "/api/deal/trace":
                from .deal_desk import trace
                name = str(req.get("name", "")).strip()[:80]
                if len(name) < 2:
                    return self._send(400, {"error": "type a product name"})
                return self._send(200, trace(name))
            if url.path == "/api/deal/report":
                from .deal_desk import real_opportunities, forecast, report, _hub_json
                opps = real_opportunities(30)
                hist = {}
                for o in opps[:10]:
                    pts = _hub_json(f"/api/products/{o['product_id']}/history?source={o['sell_source']}&hours=720") or []
                    hist[o["product_id"]] = forecast(pts)
                path, text = report(ws, opps, hist)
                return self._send(200, {"path": str(path), "text": text})
            if url.path == "/api/settings":
                cfg = ws.load_config()
                if "auto_apply" in req:
                    cfg["auto_apply"] = bool(req["auto_apply"])
                if "deal_alerts" in req:
                    cur = cfg.get("deal_alerts", {})
                    da = req["deal_alerts"] or {}
                    try:
                        if "muted" in da:
                            cur["muted"] = bool(da["muted"])
                        if "min_profit" in da:
                            cur["min_profit"] = max(0.0, min(float(da["min_profit"]), 500.0))
                        if "min_margin" in da:
                            cur["min_margin"] = max(0.0, min(float(da["min_margin"]), 100.0))
                    except (TypeError, ValueError):
                        return self._send(400, {"error": "alert settings must be numbers"})
                    cfg["deal_alerts"] = cur
                if "auto_submit" in req:
                    cfg["auto_submit"] = bool(req["auto_submit"])
                if "email" in req:   # the newest choice replaces the old one
                    email = str(req["email"]).strip()
                    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                        return self._send(400, {"error": "that doesn't look like an email address"})
                    cfg.setdefault("apply_answers", {})["email"] = email
                ws.save_config(cfg)
                return self._send(200, {"auto_apply": cfg.get("auto_apply", False)})
            if url.path == "/api/bots":
                title, goal = str(req.get("title", "")).strip(), str(req.get("goal", "")).strip()
                if not title or not goal:
                    return self._send(400, {"error": "give the bot a name and a job"})
                when = str(req.get("when", "always"))
                schedule = ({"daily_at": str(req.get("time", "09:00"))[:5]} if when == "daily" else
                            {"every_minutes": 60} if when == "hourly" else None)
                if schedule and "daily_at" in schedule:
                    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", schedule["daily_at"]):
                        return self._send(400, {"error": "time must look like 09:00"})
                task = orch.tasks.start(title, goal, schedule)
                if schedule and "daily_at" in schedule:   # a daily bot waits for its time
                    orch.tasks.set_waiting(task["id"], None, next_run_time(schedule))
                return self._send(200, task)
            if url.path == "/api/bots/stop":
                return self._send(200, {"stopped": [t["title"] for t in orch.tasks.stop(str(req.get("id", "")))]})
            if url.path == "/api/apply":
                target = str(req.get("url", ""))
                if not target.startswith("https://"):
                    return self._send(400, {"error": "need an https link to the job"})
                start_filler(ws, target)
                return self._send(200, {"ok": True})
            if url.path == "/api/resume":
                try:
                    info = set_resume(ws, text=req.get("text"), filename=req.get("name"), data_b64=req.get("data"))
                except (ValueError, OSError) as e:
                    return self._send(400, {"error": str(e)})
                orch.chat.append("user", f"[I gave HomeGrok a new resume: {info['source']}. Use it from now on.]")
                return self._send(200, info)
            if url.path == "/api/reveal":
                path = inside_results(req.get("path", ""))
                if not path or not path.exists():
                    return self._send(404, {"error": "not found"})
                subprocess.run(["open", "-R", str(path)] if path.is_file() else ["open", str(path)], check=False)
                return self._send(200, {"ok": True})
            return self._chat(req)

        def _chat(self, req):
            try:
                message = str(req["message"]).strip()[:4000]
                from .attachments import save_and_read
                attached = []
                for item in (req.get("attachments") or [])[:5]:
                    path, text = save_and_read(ws, str(item.get("name", "file")), str(item.get("data", "")))
                    attached.append({"name": path.name, "text": text})
                options = dict(
                    max_new_tokens=max(1, min(int(req.get("max_tokens", 120)), 400)),
                    temperature=max(0.0, min(float(req.get("temperature", 0.8)), 2.0)),
                    brain="local" if req.get("brain") == "local" else "auto",
                )
                if not message and not attached:
                    raise ValueError("empty message")
                if not message:
                    message = "Read the attached file(s) and answer or act on them accordingly."
            except (KeyError, ValueError, TypeError) as e:
                monitor.record({"error": f"bad request: {e}"})
                return self._send(400, {"error": f"bad request: {e}"})

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            connected = [True]

            def emit(obj):
                # If the page was closed mid-reply, keep going: the answer is still saved to history.
                if not connected[0]:
                    return
                try:
                    self.wfile.write((json.dumps(obj) + "\n").encode())
                    self.wfile.flush()
                except OSError:
                    connected[0] = False

            try:
                result = orch.answer(message, on_text=lambda piece: emit({"type": "delta", "text": piece}),
                                     attachments=attached, **options)
            except Exception as e:  # keep the server alive, but log it
                monitor.record({"error": repr(e)})
                return emit({"type": "error", "error": "internal error, see logs/requests.jsonl"})
            monitor.record({"message_chars": len(message), "brain": result["brain"], "model": result["model"],
                            "usage": result["usage"], "latency_ms": result["latency_ms"]})
            emit({"type": "done", **result})

    return Handler


def auto_apply_loop(ws, orch):
    """Auto mode: keep up to AUTO_APPLY_MAX_OPEN applications open and filling, best fits first."""
    while True:
        time.sleep(10)
        try:
            orch.answer_held()
        except Exception as e:
            print(f"[held messages] {e!r}", flush=True)
        try:
            if not ws.load_config().get("auto_apply"):
                continue
            cooldown = apply_dir(ws) / "cooldown.json"
            if cooldown.exists() and time.time() < json.loads(cooldown.read_text()).get("until", 0):
                continue   # the last window closed right away without filling: wait before trying again
            status = filler_status(ws)
            pages = status.get("pages", []) if status.get("running") else []
            in_progress = [p for p in pages if not p.get("ready") and not p.get("waiting_for_you")]
            if len(in_progress) >= AUTO_APPLY_MAX_OPEN or len(pages) >= AUTO_APPLY_MAX_WAITING:
                continue   # finish this one first; ready ones wait for your final click
            seen = set(opened(ws)) - set(retry_urls(ws))   # unfinished applications get another try
            for job in orch.scout.open_jobs(limit=40, url_filter=FILLABLE):
                if FILLABLE.search(job["url"]) and job["url"] not in seen:
                    start_filler(ws, job["url"])
                    break
        except Exception as e:  # keep the loop alive
            print(f"[auto-apply] {e!r}", flush=True)


class Server(ThreadingHTTPServer):
    daemon_threads = True


def serve(ws, port=8000):
    from .alerts import start as start_deal_alerts
    api_key = get_api_key(ws)
    orch = Orchestrator(ws)
    monitor = Monitor(ws)
    version = code_version()
    deal_alerts = start_deal_alerts(ws)   # live notifications for real deals
    httpd = Server(("127.0.0.1", port), make_handler(ws, orch, monitor, api_key, version, deal_alerts))
    threading.Thread(target=auto_apply_loop, args=(ws, orch), daemon=True).start()

    print(f"HomeGrok {version} running at http://127.0.0.1:{port}  (local model: {orch.server.name or 'none yet'})",
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
