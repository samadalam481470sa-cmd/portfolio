"""Serving path: Model server + Orchestrator.

The orchestrator answers each message with the best brain available:
  * Claude, through your Claude subscription (see brain.py), given HomeGrok's memory of
    you, the passages from your files that match the question, and your running tasks.
    When you ask for ongoing work, Claude starts a background task (see tasks.py);
  * otherwise HomeGrok's own local model, which the autopilot keeps training on your files.
The model server holds the local model in memory and hot-swaps it whenever training
promotes a better one. The conversation is kept in workspace/chat.jsonl so it is still
there whenever you open the page.
"""
import json
import re
import threading
import time

import torch

from .brain import BrainUnavailable, ClaudeBrain, UsageLimitReached, format_time
from .chatlog import ChatLog
from .config import pick_device
from . import localllm
from .jobs import JobScout, format_jobs
from .memory import Memory
from .profile import current_resume
from .storage import current_model_info, load_checkpoint
from .tasks import Tasks
from .tokenizer import Tokenizer
from .vectordb import load_index

CHAT_SYSTEM = (
    "You are HomeGrok, the user's personal AI, like Grok but running on their Mac. You know their files and "
    "what they told you, you can search the web and read pages in real time, and you keep working for them in "
    "the background. Messages may include a memory note about the user, excerpts from their files, job postings "
    "that HomeGrok's Job Scout just confirmed are open on the companies' own job boards, and the background "
    "tasks you are running. Use what is relevant.\n\n"
    "- Answer like Claude with web search: for facts, news, prices, events, companies and jobs, search the web "
    "instead of guessing, and link your sources. Don't rely on the user's computer files.\n"
    "- When asked for jobs or internships, recommend postings from the confirmed-open list first, with their "
    "direct links and posting dates. Only add others you have opened yourself and confirmed are still accepting "
    "applications. Never list postings you haven't confirmed.\n"
    "- You can take on ongoing work that runs around the clock, for example writing a tailored resume and cover "
    "letter for each good new posting. When the user asks for ongoing work, say briefly what you'll do and end "
    "your reply with exactly one line:\n"
    "[[START TASK: short title || complete description of the goal, with every preference they gave]]\n"
    "When they ask you to stop one, end your reply with: [[STOP TASK: title of the task]]\n"
    "Only add these lines when the user asks to start or stop ongoing work.\n"
    "- To fill out a job application for the user, end your reply with: [[FILL APPLICATION: https://link-to-the-posting]]. "
    "HomeGrok then opens it in a Chrome window on their screen, fills in their details and resume, and stops "
    "before Submit so they can review and submit it. It can't sign in, create accounts or solve CAPTCHAs.\n"
    "- In this chat you can't create, edit or delete files, and you never submit applications, send messages or "
    "sign in anywhere. Background tasks write new files to ~/HomeGrok Results; don't promise to change files "
    "that already exist. The user reviews and submits each application.\n"
    "- You can write and run your own Python whenever it helps (calculations, data, text processing, making "
    "files). Put the code in a block that starts with ```python-run and HomeGrok runs it immediately in a locked "
    "sandbox: no internet, no access to the user's files, 60 seconds max. Its output is added under your reply.\n"
    "Be direct and concise."
)
RUN_BLOCK = re.compile(r"```python-run\s*\n(.*?)```", re.S)
START_TAG = re.compile(r"\[\[\s*START TASK:\s*(.+?)\s*\|\|\s*(.+?)\s*\]\]", re.S)
STOP_TAG = re.compile(r"\[\[\s*STOP TASK:\s*(.+?)\s*\]\]", re.S)
FILL_TAG = re.compile(r"\[\[\s*FILL APPLICATION:\s*(https://\S+?)\s*\]\]")
JOB_INTENT = re.compile(r"\b(jobs?|intern(ship)?s?|positions?|openings?|hiring|postings?|roles?|careers?)\b", re.I)
QUERY_STOPWORDS = {"find", "show", "give", "list", "recent", "latest", "newest", "good", "best", "some", "more",
                   "jobs", "internships", "internship", "positions", "openings", "postings", "roles", "careers",
                   "hiring", "that", "with", "near", "what", "which", "where", "there", "have", "please", "want",
                   "need", "looking", "apply", "quality", "real", "bogus", "today", "week", "this", "these",
                   "from", "for", "and", "any", "new", "me", "my"}
CHAT_TOOLS = ("WebSearch", "WebFetch")
DEAL_INTENT = re.compile(r"\b(deals?|profit\w*|resell\w*|wholesale|arbitrage|hub|trending|margin|buy low|flip\w*)\b", re.I)


def relevant_sources(hits):
    """Keep only file passages that clearly match, so unrelated files aren't shown or sent."""
    if not hits:
        return []
    top = hits[0]["score"]
    return [h for h in hits if h["score"] >= max(4.5, 0.45 * top)]


class ModelServer:
    def __init__(self, ws):
        self.ws = ws
        self.device = pick_device()
        self.lock = threading.Lock()
        self.name = None
        self.model = None
        self.info = None
        self.tok = Tokenizer.load(ws.tokenizer) if ws.tokenizer.exists() else None
        self._registry_mtime = None
        self.maybe_reload()

    def maybe_reload(self):
        """Pick up a newly promoted model without restarting the server."""
        if not self.ws.registry.exists():
            return
        mtime = self.ws.registry.stat().st_mtime
        if mtime == self._registry_mtime:
            return
        self._registry_mtime = mtime
        name, info = current_model_info(self.ws)
        if name and name != self.name:
            model, _ = load_checkpoint(info["path"], self.device)
            model.eval()
            with self.lock:
                self.model, self.name, self.info = model, name, info
                self.tok = Tokenizer.load(self.ws.tokenizer)
            print(f"[model server] now serving {name}")

    def generate(self, prompt_ids, max_new_tokens, temperature, top_k=50, top_p=0.95):
        with self.lock:
            budget = self.model.cfg.block_size - 1
            prompt_ids = prompt_ids[-budget:] or [self.tok.eot]
            idx = torch.tensor([prompt_ids], device=self.device)
            out = self.model.generate(idx, max_new_tokens, temperature, top_k, top_p,
                                      stop_ids={self.tok.eot})
            return out[0, len(prompt_ids):].tolist()


class Orchestrator:
    def __init__(self, ws):
        self.ws = ws
        self.server = ModelServer(ws)
        self.brain = ClaudeBrain(ws)
        self.memory = Memory(ws)
        self.tasks = Tasks(ws)
        self.scout = JobScout(ws)
        self.chat = ChatLog(ws)
        self.index = load_index(ws)
        self._index_mtime = ws.index.stat().st_mtime if ws.index.exists() else None

    def _maybe_reload_index(self):
        if self.ws.index.exists() and self.ws.index.stat().st_mtime != self._index_mtime:
            self.index = load_index(self.ws)
            self._index_mtime = self.ws.index.stat().st_mtime

    def answer(self, message, max_new_tokens=120, temperature=0.8, brain="auto", on_text=None, attachments=None):
        """Answer one message. on_text(piece) receives Claude's reply as it is written."""
        start = time.time()
        self.server.maybe_reload()
        self._maybe_reload_index()
        history = [{"role": e["role"], "text": e["text"]} for e in self.chat.recent(8)]
        names = [a["name"] for a in (attachments or [])]
        self.chat.append("user", message + (f"  [attached: {', '.join(names)}]" if names else ""))
        sources = []   # answers come from the web and what you told HomeGrok, not your computer files
        note = None

        result = None
        deals = []
        if DEAL_INTENT.search(message):   # read-only lookup in the Wholesale Hub (never changes its data)
            from .connections import hub_deals
            deals = hub_deals(limit=8)
        self._attachments = attachments or []
        if brain != "local" and self.brain.enabled:
            jobs = []
            if JOB_INTENT.search(message):
                terms = [w for w in re.findall(r"[a-z]{3,}", message.lower()) if w not in QUERY_STOPWORDS]
                try:
                    jobs = self.scout.open_jobs(extra_terms=terms, limit=12)
                except Exception:  # job boards unreachable: Claude still searches the web itself
                    jobs = []
            try:
                result = self._answer_with_claude(message, history, sources, jobs, on_text, deals)
            except UsageLimitReached as e:
                result = self._answer_with_open_model(message, history, on_text,
                                                      f"Your Claude plan is used up until {format_time(e.resets_at)}; "
                                                      "this answer comes from the open model on your Mac.")
                if result is None:
                    self._hold(message)
                    result = {"reply": f"Your Claude plan's limit is used up until {format_time(e.resets_at)}. I saved your "
                                   "message and will answer it here automatically as soon as it resets.",
                          "brain": "waiting", "model": None, "actions": [], "sources": [],
                          "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "note": None}
            except BrainUnavailable as e:
                note = f"Claude is unavailable ({e}), so the open model on your Mac answered."
                result = self._answer_with_open_model(message, history, on_text, note)
        if result is None and brain == "local":
            result = self._answer_with_open_model(message, history, on_text, None)
        if result is None:
            result = self._answer_locally(message, history, sources[:4], max_new_tokens, temperature)
            result["note"] = note
        result["latency_ms"] = int((time.time() - start) * 1000)
        self.chat.append("assistant", result["reply"], brain=result["brain"], model=result["model"],
                         note=result.get("note"), actions=result.get("actions", []),
                         sources=[s["path"] for s in result["sources"]])
        return result

    def _answer_with_open_model(self, message, history, on_text, note):
        """Answer with Llama 3.2 on the Mac's GPU, or None if it isn't installed or running."""
        if not localllm.available():
            return None
        try:
            text = localllm.chat(message, history, on_text)
        except Exception:
            return None
        return {"reply": text.strip(), "brain": "ollama", "model": localllm.MODEL, "actions": [], "sources": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "note": note}

    def _hold(self, message):
        path = self.ws.root / "pending_chat.json"
        pending = json.loads(path.read_text()) if path.exists() else []
        path.write_text(json.dumps(pending + [{"message": message, "time": time.time()}]))

    def answer_held(self):
        """Answer messages that arrived while Claude was out of usage (called every half minute)."""
        path = self.ws.root / "pending_chat.json"
        if not path.exists() or not self.brain.status()["available"]:
            return
        pending = json.loads(path.read_text())
        path.unlink()
        for item in pending:
            self.answer(f"(You asked this at {time.strftime('%-I:%M %p', time.localtime(item['time']))}, while "
                        f"Claude was out of usage.) {item['message']}")

    def _tasks_context(self):
        lines = []
        for t in self.tasks.all()[-10:]:
            latest = t["log"][-1]["summary"] if t["log"] else "no steps yet"
            lines.append(f"- {t['title']} [{t['status']}]: {t['steps']} steps, {len(t['files'])} files in "
                         f"{t['folder']}. Latest: {latest}")
        return "\n".join(lines)

    def _answer_with_claude(self, message, history, sources, jobs, on_text, deals=()):
        parts = []
        resume = current_resume(self.ws)
        if resume:
            parts.append(f"<current_resume>\n{resume[:12000]}\n</current_resume>")
        said = self.chat.user_messages(25)   # what you told HomeGrok yourself (not your computer files)
        if said:
            parts.append("<what_the_user_told_you>\n" + "\n".join(f"- {m}" for m in said) + "\n</what_the_user_told_you>")
        if sources:
            excerpts = "\n".join(f'<excerpt file="{s["path"]}">\n{s["text"]}\n</excerpt>' for s in sources)
            parts.append(f"<files>\n{excerpts}\n</files>")
        for att in getattr(self, "_attachments", []):   # attached files: read as data, answered directly
            parts.append(f"<attachment name=\"{att['name']}\">\n{att['text']}\n</attachment>\n"
                         "The attachment above was given by the user. Read it and answer or act on it as they asked.")
        if deals:
            lines = [f"- {d.get('product_name') or d.get('name', '?')}: profit ${d.get('profit', 0):.2f}, "
                     f"margin {d.get('margin_pct', 0):.0f}%, buy at {d.get('buy_store', '?')}, sell at "
                     f"{d.get('sell_store', '?')}" for d in deals]
            parts.append("<wholesale_hub_deals checked=\"" + time.strftime('%b %d %H:%M') + "\">\n"
                         + "\n".join(lines) + "\n</wholesale_hub_deals>")
        if jobs:
            parts.append(f"<confirmed_open_jobs checked=\"{time.strftime('%b %d %H:%M')}\">\n"
                         f"{format_jobs(jobs)}\n</confirmed_open_jobs>")
        tasks = self._tasks_context()
        if tasks:
            parts.append(f"<background_tasks>\n{tasks}\n</background_tasks>")
        if history:
            turns = "\n".join(f"{t['role']}: {t['text']}" for t in history[-6:])
            parts.append(f"<conversation>\n{turns}\n</conversation>")
        try:   # one search across every source HomeGrok has (public text, jobs, deals, saved answers, chat)
            from .knowledge import search as knowledge_search
            hits = knowledge_search(self.ws, message, k=6)
            if hits:
                block = "\n".join(f"[{h['id']}] ({h['label']}) {h['title']}: {h['text'][:500]}" for h in hits)
                parts.append(f"<knowledge>\n{block}\n</knowledge>\nWhen you use a knowledge source, cite its number like [2].")
        except Exception:
            pass   # the chat still answers without it
        parts.append(f"(Today is {time.strftime('%A, %B %d, %Y')}.)\n\n{message}")
        reply = self.brain.ask("\n\n".join(parts), CHAT_SYSTEM, kind="chat", tools=CHAT_TOOLS, on_text=on_text)

        text, actions = reply["text"], []
        for title, goal in START_TAG.findall(text):
            task = self.tasks.start(title, goal)
            actions.append({"type": "started", "title": task["title"], "folder": task["folder"]})
        for query in STOP_TAG.findall(text):
            for task in self.tasks.stop(query):
                actions.append({"type": "stopped", "title": task["title"]})
        for link in FILL_TAG.findall(text):
            from .apply import start as start_filler
            start_filler(self.ws, link)
            actions.append({"type": "filling", "title": link})
        text = FILL_TAG.sub("", STOP_TAG.sub("", START_TAG.sub("", text))).strip()
        for code in RUN_BLOCK.findall(text):   # HomeGrok's own code, run in the sandbox
            from .sandbox import run_python
            r = run_python(code, self.ws)
            text += (f"\n\n**Ran my code** ({r['seconds']} s, {'ok' if r['ok'] else 'error'}):\n```\n"
                     f"{r['output'].strip()[:4000] or '(no output)'}\n```")
            if r["files"]:
                text += f"\nFiles it made: {', '.join(r['files'])} in {r['folder']}"
        return {
            "reply": text,
            "brain": "claude",
            "model": reply["model"],
            "actions": actions,
            "sources": [{"path": s["path"], "score": s["score"], "snippet": s["text"][:400]} for s in sources],
            "usage": {"prompt_tokens": reply["input_tokens"], "completion_tokens": reply["output_tokens"]},
            "note": None,
        }

    def _answer_locally(self, message, history, sources, max_new_tokens, temperature):
        reply, prompt_tokens, completion_tokens = "", 0, 0
        if self.server.model is not None:
            tok = self.server.tok
            # Retrieved passages first, then recent conversation, then the new message.
            context = "\n\n".join(s["text"] for s in reversed(sources[:2]))
            convo = "\n".join(f"{t['role']}: {t['text']}" for t in history[-4:])
            prompt = "\n\n".join(p for p in (context, convo, message) if p) + "\n"
            prompt_ids = tok.encode(prompt)
            out = self.server.generate(prompt_ids, max_new_tokens, temperature)
            reply = tok.decode(out).strip()
            prompt_tokens = min(len(prompt_ids), self.server.model.cfg.block_size - 1)
            completion_tokens = len(out)
        return {
            "reply": reply,
            "brain": "local",
            "model": self.server.name,
            "actions": [],
            "sources": [{"path": s["path"], "score": s["score"], "snippet": s["text"][:400]} for s in sources],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        }
