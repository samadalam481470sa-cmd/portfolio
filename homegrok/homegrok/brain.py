"""Claude as HomeGrok's brain, through your own Claude subscription.

HomeGrok runs the Claude Code CLI in headless mode (`claude -p`). The CLI signs in with
your Claude account, so every call counts against your plan's usage limits instead of a
separate API bill. Calls run with your Claude Code customizations switched off and only
the tools HomeGrok asks for: none for chat, web search and web fetch for background
tasks. Claude can never read your disk, run commands or act on websites.

Every call also reports how much of your 5-hour and weekly limits is used. Background
work stops while either is above (1 - background_reserve), leaving the rest for you, and
everything resumes on its own when the limit resets.
"""
import fcntl
import json
import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

CLI_CANDIDATES = ("~/.local/bin/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude",
                  "~/.claude/local/claude")
DEFAULTS = {
    "enabled": False,
    "cli": None,
    "chat_model": None,          # None = whatever your Claude Code uses by default
    "background_model": None,
    "chat_effort": "medium",
    "background_effort": "low",
    "background_calls_per_day": None,   # None = no daily cap; the usage reserve still applies
    "background_reserve": 0.10,         # share of each usage window kept free for you
}
WINDOW_NAMES = {"five_hour": "5-hour", "seven_day": "weekly"}
USAGE_LIMIT = re.compile(r"usage limit|limit reached|hit your (?:usage )?limit|out of (?:extra )?usage|"
                         r"weekly limit|session limit|5-hour limit", re.I)
NOT_SIGNED_IN = re.compile(r"/login|not logged in|invalid api key|oauth token|authentication", re.I)


class BrainUnavailable(Exception):
    """Claude can't be used right now; HomeGrok falls back to its local model."""


class UsageLimitReached(BrainUnavailable):
    def __init__(self, message, resets_at):
        super().__init__(message)
        self.resets_at = resets_at


class DailyCapReached(BrainUnavailable):
    pass


def parse_reset(text, now=None):
    """Find when a usage limit resets in Claude's message. Returns a unix time or None."""
    now = now or datetime.now()
    m = re.search(r"\|(\d{10})\b", text)  # "Claude AI usage limit reached|1760468400"
    if m:
        return float(m.group(1))
    m = re.search(r"resets?\s+(?:at\s+)?(?:([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(?:at\s+)?)?"
                  r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)", text, re.I)
    if not m:
        return None
    month, day, hour, minute, ampm = m.groups()
    hour = int(hour) % 12 + (12 if ampm.lower().startswith("p") else 0)
    when = now.replace(hour=hour, minute=int(minute or 0), second=0, microsecond=0)
    if month and day:
        try:
            when = when.replace(month=datetime.strptime(month[:3].title(), "%b").month, day=int(day))
        except ValueError:
            pass
        if when < now - timedelta(days=1):
            when = when.replace(year=when.year + 1)
    elif when <= now:
        when += timedelta(days=1)
    return when.timestamp()


def find_cli(configured=None):
    for candidate in filter(None, (configured, shutil.which("claude"), *CLI_CANDIDATES)):
        path = Path(candidate).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def _clean_env(cli):
    # Drop variables inherited from any Claude Code session HomeGrok was started from, and any
    # API key, so the CLI always signs in with your own Claude account.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE", "ANTHROPIC_")) or k == "CLAUDE_CONFIG_DIR"}
    env.setdefault("HOME", str(Path.home()))
    env["PATH"] = os.pathsep.join([str(Path(cli).parent), env.get("PATH", ""), "/usr/bin:/bin:/usr/sbin:/sbin"])
    return env


def _loads_loose(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def format_time(ts):
    when = datetime.fromtimestamp(ts)
    fmt = "%-I:%M %p" if when.date() == datetime.now().date() else "%a %b %-d, %-I:%M %p"
    return when.strftime(fmt)


class ClaudeBrain:
    def __init__(self, ws):
        self.ws = ws
        self.state_path = ws.root / "brain_state.json"
        self.lock_path = ws.root / "brain_state.lock"
        self.sandbox = ws.root / "claude_sandbox"   # empty working folder for the CLI
        self.sandbox.mkdir(exist_ok=True)

    @property
    def settings(self):
        return {**DEFAULTS, **self.ws.load_config().get("claude", {})}

    @property
    def enabled(self):
        return bool(self.settings["enabled"])

    @contextmanager
    def _state(self):
        """Read-modify-write the shared usage state under a lock (the server and the learner both use it)."""
        with open(self.lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
            today = time.strftime("%Y-%m-%d")
            if state.get("day") != today:
                state.update(day=today, calls={"chat": 0, "background": 0}, tokens={"input": 0, "output": 0})
            yield state
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            os.replace(tmp, self.state_path)

    def _wait_reason(self, st, kind):
        """(message, resets_at) if a call of this kind has to wait, else None."""
        now = time.time()
        if st.get("blocked_until", 0) > now:
            return st.get("block_reason") or "Claude usage limit reached", st["blocked_until"]
        if kind == "background":
            stop_at = 1 - self.settings["background_reserve"]
            for name, window in (st.get("limits") or {}).items():
                if window.get("resetsAt", 0) > now and window.get("utilization", 0) >= stop_at:
                    return (f"{round(window['utilization'] * 100)}% of your {WINDOW_NAMES.get(name, name)} "
                            "Claude limit is used, so background work waits and the rest stays yours",
                            window["resetsAt"])
        return None

    def status(self):
        s = self.settings
        with self._state() as st:
            st = dict(st)
        cli = find_cli(s["cli"])
        waiting = self._wait_reason(st, "chat")
        background_wait = self._wait_reason(st, "background")
        now = time.time()
        limits = [{"name": WINDOW_NAMES.get(name, name), "used": round(w.get("utilization", 0) * 100),
                   "resets_at": format_time(w["resetsAt"]) if w.get("resetsAt") else None}
                  for name, w in (st.get("limits") or {}).items() if w.get("resetsAt", 0) > now]
        return {
            "enabled": s["enabled"],
            "cli_found": bool(cli),
            "available": bool(s["enabled"] and cli and not waiting),
            "blocked_until": waiting[1] if waiting else None,
            "resets_at": format_time(waiting[1]) if waiting else None,
            "background_waiting": background_wait[0] if background_wait else None,
            "background_resumes_at": format_time(background_wait[1]) if background_wait else None,
            "limits": limits,
            "calls_today": st["calls"],
            "background_cap": s["background_calls_per_day"],
            "tokens_today": st["tokens"],
            "model": st.get("last_model"),
            "last_error": st.get("last_error"),
        }

    def _record_error(self, message):
        with self._state() as st:
            st["last_error"] = {"time": time.time(), "message": message[:300]}

    def ask(self, prompt, system, kind="chat", json_schema=None, tools=(), on_text=None, timeout=300, effort=None):
        """Send one prompt to Claude and return its reply.

        kind: "chat" (you asked) or "background" (autopilot work).
        tools: built-in Claude Code tools to allow, e.g. ("WebSearch", "WebFetch").
        on_text: called with each piece of the reply as it is written.
        """
        s = self.settings
        if not s["enabled"]:
            raise BrainUnavailable("Claude is turned off (run ./hg claude --enable)")
        cli = find_cli(s["cli"])
        if not cli:
            raise BrainUnavailable("the claude command isn't installed")
        with self._state() as st:
            waiting = self._wait_reason(st, kind)
            if waiting:
                raise UsageLimitReached(*waiting)
            cap = s["background_calls_per_day"]
            if kind == "background" and cap and st["calls"]["background"] >= cap:
                raise DailyCapReached(f"today's {cap} background Claude calls are used up")

        args = [cli, "-p", "--output-format", "stream-json", "--verbose", "--safe-mode",
                "--tools", ",".join(tools), "--strict-mcp-config", "--no-session-persistence",
                "--permission-prompts", "none", "--system-prompt", system]
        if tools:
            args += ["--allowedTools", ",".join(tools)]
        if on_text:
            args.append("--include-partial-messages")
        if s[f"{kind}_model"]:
            args += ["--model", s[f"{kind}_model"]]
        if effort or s[f"{kind}_effort"]:
            args += ["--effort", effort or s[f"{kind}_effort"]]
        if json_schema:
            args += ["--json-schema", json.dumps(json_schema)]

        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, cwd=self.sandbox, env=_clean_env(cli))
        watchdog = threading.Timer(timeout, proc.kill)
        watchdog.start()
        result, limits, other = None, {}, []
        try:
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except OSError:  # the CLI exited early; its output below says why
                pass
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    other.append(line.strip())
                    continue
                kind_ = event.get("type")
                if kind_ == "stream_event" and on_text:
                    inner = event.get("event") or {}
                    delta = inner.get("delta") or {}
                    if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        on_text(delta.get("text", ""))
                elif kind_ == "rate_limit_event":
                    info = event.get("rate_limit_info") or {}
                    limits = info.get("unifiedWindows") or limits
                elif kind_ == "result":
                    result = event
            proc.wait()
        finally:
            timed_out = not watchdog.is_alive() and proc.returncode not in (0, None) and result is None
            watchdog.cancel()

        if limits:
            with self._state() as st:
                st["limits"] = limits
                st["limits_updated"] = time.time()
        if result is None:
            if timed_out:
                raise BrainUnavailable(f"Claude didn't finish within {timeout} seconds")
            detail = " ".join(other)[-300:] or f"exit code {proc.returncode}"
            self._record_error(detail)
            if NOT_SIGNED_IN.search(detail):
                raise BrainUnavailable("Claude Code isn't signed in. Run `claude` in Terminal and log in")
            raise BrainUnavailable(f"the Claude CLI failed: {detail}")

        text = result.get("result") or ""
        if result.get("is_error"):
            if result.get("api_error_status") == 429 or USAGE_LIMIT.search(text):
                resets = parse_reset(text) or max((w.get("resetsAt", 0) for w in limits.values()), default=0) \
                    or time.time() + 3600
                with self._state() as st:
                    st["blocked_until"] = resets
                    st["block_reason"] = text[:200] or "Claude usage limit reached"
                raise UsageLimitReached(text or "Claude usage limit reached", resets)
            self._record_error(text or "unknown error")
            if NOT_SIGNED_IN.search(text):
                raise BrainUnavailable("Claude Code isn't signed in. Run `claude` in Terminal and log in")
            raise BrainUnavailable(text[:200] or "Claude returned an error")

        usage = result.get("usage") or {}
        tokens_in = sum(usage.get(k) or 0 for k in
                        ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        tokens_out = usage.get("output_tokens") or 0
        model = next(iter(result.get("modelUsage") or {}), s[f"{kind}_model"] or "claude")
        with self._state() as st:
            st["calls"][kind] += 1
            st["tokens"]["input"] += tokens_in
            st["tokens"]["output"] += tokens_out
            st["last_model"] = model
            st["last_error"] = None
            st.pop("blocked_until", None)
            st.pop("block_reason", None)
        structured = result.get("structured_output")
        if json_schema and not isinstance(structured, dict):
            structured = _loads_loose(text)
        return {"text": text, "data": structured, "model": model,
                "input_tokens": tokens_in, "output_tokens": tokens_out}
