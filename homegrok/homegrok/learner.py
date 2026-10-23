"""Autopilot: HomeGrok's 24/7 background worker. It never needs to be started or paused.

It runs a team of bots, one cycle after another:
  * Job Scout     downloads public internship and new-grad listings and confirms the best-fitting
                  postings are still open on the companies' own job boards (no Claude usage);
  * Web Learner   adds public text (Wikipedia, job postings) to the local model's corpus;
  * Task bots     the standing tasks you started in the chat, e.g. writing tailored resumes
                  (Claude), whenever the Mac is online;
  * Memory        Claude reads new or changed files of yours and what you said in chat;
  * Trainer       trains HomeGrok's own model on the public corpus on the Mac's GPU (rests on
                  battery and once it stops improving, until the corpus grows).
Claude work stops while your usage is near its limit and resumes on its own after the reset.
Everything goes to an activity feed that the web page shows live.
"""
import json
import os
import re
import shutil
import tarfile
from pathlib import Path
import socket
import subprocess
import time

from .brain import BrainUnavailable, ClaudeBrain, DailyCapReached, UsageLimitReached, format_time
from .evolve import Evolution
from .jobs import JobScout
from .memory import Memory
from .refresh import refresh_data
from .storage import reset_local_models
from .tasks import Tasks
from .tokenizer import train_tokenizer
from .train import NotEnoughData
from .vectordb import load_index
from .webcorpus import MIN_TOKENIZER_CHARS, PublicCorpus, learn_from_web

ACTIVITY_MAX_BYTES = 512 * 1024
FILLABLE = re.compile(r"greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com")
PLATEAU_GENERATIONS = 3   # generations without a new live model before local training rests
CORPUS_GROWTH = 0.05
BACKUP_DIR = Path.home() / "HomeGrok Backups"
BACKUP_HOURS = 1
BACKUP_KEEP = 48
# Everything that can't be rebuilt from your files or the internet.
BACKUP_ITEMS = ("config.json", "chat.jsonl", "tasks.json", "memory", "profile", "brain_state.json", "jobs.db",
                "api_key", "logs/usage.json")


def backup(ws):
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / time.strftime("homegrok-%Y%m%d-%H%M.tar.gz")
    with tarfile.open(target, "w:gz") as tar:
        for item in BACKUP_ITEMS:
            if (ws.root / item).exists():
                tar.add(ws.root / item, arcname=item)
    for old in sorted(BACKUP_DIR.glob("homegrok-*.tar.gz"))[:-BACKUP_KEEP]:
        old.unlink()
    return target      # corpus growth that wakes resting training up again


def filler_open(ws):
    from .apply import read_status
    return bool(read_status(ws).get("running"))


def low_on_memory():
    """True when free RAM + remaining swap is tight, so heavy GPU training should wait."""
    try:
        out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5).stdout
        free_swap = float(re.search(r"free = ([\d.]+)M", out).group(1))
        return free_swap < 1024   # under 1 GB of swap headroom
    except Exception:
        return False


def on_battery():
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "Battery Power" in out


def online(host="api.anthropic.com", port=443, timeout=4):
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


def status_path(ws):
    return ws.root / "learner.json"


def activity_path(ws):
    return ws.logs / "activity.jsonl"


def read_status(ws, activity=12):
    try:
        status = json.loads(status_path(ws).read_text())
    except (OSError, ValueError):
        status = {"state": "off"}
    # The autopilot rewrites its status at least every few minutes; silence means it isn't running.
    if status.get("updated") and time.time() - status["updated"] > 20 * 60:
        status["state"] = "off"
    try:
        with open(activity_path(ws), encoding="utf-8") as f:
            lines = f.readlines()[-activity:]
        status["activity_log"] = [json.loads(line) for line in reversed(lines)]
    except (OSError, ValueError):
        status["activity_log"] = []
    return status


class Autopilot:
    def __init__(self, ws, population=4, minutes_per=2.0, digests_per_cycle=5, train_on_battery=False):
        self.ws = ws
        self.population = population
        self.minutes_per = minutes_per
        self.digests_per_cycle = digests_per_cycle
        self.train_on_battery = train_on_battery
        self.brain = ClaudeBrain(ws)
        self.memory = Memory(ws)
        self.tasks = Tasks(ws)
        self.scout = JobScout(ws)
        self.corpus = PublicCorpus(ws)
        self.evo = None
        self.unimproved = 0
        self.trained_on_chars = 0
        self.status = {"state": "starting", "started": time.time(), "cycle": 0}
        self._last_message = None

    def _write_status(self):
        self.status["updated"] = time.time()
        tmp = status_path(self.ws).with_suffix(".tmp")
        tmp.write_text(json.dumps(self.status))
        os.replace(tmp, status_path(self.ws))

    def say(self, message, state=None):
        """Record what the autopilot is doing right now; the web page shows it live."""
        if state:
            self.status["state"] = state
        self.status["activity"] = message
        self._write_status()
        if message == self._last_message:
            return
        self._last_message = message
        print(time.strftime("%H:%M:%S"), message, flush=True)
        path = activity_path(self.ws)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), "message": message}) + "\n")
        if path.stat().st_size > ACTIVITY_MAX_BYTES:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)[-500:]
            path.write_text("".join(lines), encoding="utf-8")

    def _task_due(self):
        due_at = self.tasks.next_due_at()
        return due_at is not None and due_at <= time.time() and self.brain.enabled

    def _wait(self, seconds):
        """Sleep, but wake up as soon as a task is added or becomes due."""
        tasks_changed = self.tasks.changed_at()
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(3)
            if self.tasks.changed_at() != tasks_changed or self._task_due():
                return
        self._write_status()

    # -- bots -------------------------------------------------------------------
    def _job_scout(self):
        if self.scout.refresh_due():
            self.say("Job Scout: downloading the latest internship and new-grad listings", "scanning")
            self.scout.refresh(log=self.say)
        before = self.scout.stats()["verified_open"]
        self.scout.open_jobs(limit=15)   # keep the best fits confirmed, so answers are instant
        self.scout.open_jobs(limit=15, url_filter=FILLABLE)   # and ones HomeGrok can fill without an account
        found = self.scout.stats()["verified_open"] - before
        if found > 0:
            self.say(f"Job Scout: confirmed {found} more postings are open on the companies' own sites")

    def _public_vocabulary_ready(self):
        return self.corpus.meta().get("tokenizer_ready", False)

    def _web_learner(self):
        ready = self._public_vocabulary_ready()
        batches = 1 if ready else 25   # gather a starter corpus quickly the first time
        learn_from_web(self.ws, self.scout, batches=batches, log=lambda m: self.say(m, "learning"))
        try:   # online learning: open sources only, robots.txt checked, daily cap
            from .online_learning import learn_online
            if online():
                learn_online(self.ws, log=lambda m: self.say(m, "learning"))
        except Exception as e:
            self.say(f"Online learning paused this round ({e!r})")
        try:   # the Cortex learns the new public text (never personal files)
            from .cortex_bot import PublicCortex
            learned = PublicCortex(self.ws).learn_new()
            if learned:
                self.say(f"Cortex: learned {learned} new public documents", "learning")
        except Exception as e:   # a failure here must not stop the autopilot
            self.say(f"Cortex: could not learn this round ({e!r})")
        meta = self.corpus.meta()
        if not ready and meta["chars"] >= MIN_TOKENIZER_CHARS:
            self.say("Web Learner: building HomeGrok's vocabulary from public text", "training")
            train_tokenizer(self.ws, vocab_size=4096, log=lambda *_: None)
            reset_local_models(self.ws)
            meta["tokenizer_ready"] = True
            self.corpus._save_meta(meta)
            self.evo, self.unimproved = None, 0
            self.say("Web Learner: vocabulary ready; HomeGrok's own model now learns from public text only")

    def _work_on_tasks(self):
        """Run due task steps until none is due. Returns False if Claude can't be used right now."""
        while True:
            task = self.tasks.due()
            if not task:
                return True
            if not online():
                self.tasks.set_waiting(task["id"], "Waiting for an internet connection", time.time() + 60)
                self.say("Offline: tasks continue as soon as the Mac is back on WiFi", "waiting")
                return False
            try:
                self.tasks.run_step(task, self.brain, self.memory, load_index(self.ws), self.scout,
                                    log=lambda m: self.say(m, "working"))
            except UsageLimitReached as e:
                for t in self.tasks.active():
                    self.tasks.set_waiting(t["id"], f"Claude usage: resumes {format_time(e.resets_at)}", e.resets_at)
                self.say(f"{e} Tasks resume at {format_time(e.resets_at)}", "waiting")
                return False
            except BrainUnavailable as e:
                self.tasks.set_waiting(task["id"], f"Claude unavailable: {e}", time.time() + 300)
                self.say(f"Claude is unavailable ({e}); trying \"{task['title']}\" again in 5 minutes", "waiting")
                return False

    def _learn_with_claude(self):
        pending = self.memory.pending()
        try:
            if pending:
                done = self.memory.learn(self.brain, self.digests_per_cycle,
                                         log=lambda m: self.say(m, "learning"))
                self.say(f"Memory: Claude read {done} file{'s' * (done != 1)}; {max(0, len(pending) - done)} still to read")
            else:
                self.memory.refresh_note(self.brain, log=lambda m: self.say(m, "learning"))
        except UsageLimitReached as e:
            self.say(f"{e} Memory resumes at {format_time(e.resets_at)}", "waiting")
        except DailyCapReached as e:
            self.say(f"Memory is done for today: {e}")
        except BrainUnavailable as e:
            self.say(f"Claude is unavailable: {e}")

    def _update_counts(self):
        self.status["memory"] = {"digested": len(self.memory.digests()), "pending": len(self.memory.pending()),
                                 "note_updated": self.memory.note_updated()}
        self.status["corpus"] = self.corpus.meta()

    def _train(self):
        if not self._public_vocabulary_ready():
            self._wait(30)   # still gathering the starter corpus
            return
        chars = self.corpus.meta()["chars"]
        if chars > self.trained_on_chars * (1 + CORPUS_GROWTH):
            self.unimproved = 0   # new text to learn from
            if self.evo:
                self.evo.reload_data()
            self.trained_on_chars = chars
        if self.unimproved >= PLATEAU_GENERATIONS:
            self.say("Trainer: learned what it can from the current corpus; resumes as it grows", "idle")
            self._wait(600)
            return
        if not self.train_on_battery and on_battery():
            self.say("Trainer: GPU training waits until the Mac is plugged in", "idle")
            self._wait(300)
            return
        if low_on_memory():
            self.say("Trainer: paused to keep the Mac responsive (low on memory)", "idle")
            self._wait(180)
            return
        try:
            if self.evo is None:
                self.evo = Evolution(self.ws, population=self.population, minutes_per=self.minutes_per,
                                     log=lambda *_: None)
                self.trained_on_chars = chars
        except NotEnoughData:
            self._wait(120)
            return
        gen = self.evo.generation
        result = self.evo.step(
            should_stop=lambda: self._task_due() or (not self.train_on_battery and on_battery()),
            on_individual=lambda ind, i, n: self.say(
                f"Trainer: training HomeGrok's own model on the GPU (generation {gen}, candidate {i} of {n})",
                "training"))
        if result:
            self.unimproved = 0 if result["promoted"] else self.unimproved + 1
            self.status.update(generation=self.evo.generation, best_loss=result["best"])
            self.say(f"Trainer: generation {gen} done, best validation loss {result['best']:.3f}"
                     + (" (new live model)" if result["promoted"] else ""))

    def _backup(self):
        latest = max((p.stat().st_mtime for p in BACKUP_DIR.glob("homegrok-*.tar.gz")), default=0) \
            if BACKUP_DIR.exists() else 0
        if time.time() - latest > BACKUP_HOURS * 3600:
            self.say(f"Backup saved: {backup(self.ws).name}")

    def cycle(self):
        self.status["cycle"] += 1
        self._backup()
        self.say("Checking your folders for new or changed files", "scanning")
        refresh_data(self.ws, log=lambda m: self.say(m))

        if online():
            self._job_scout()
            self._web_learner()
        if self.brain.enabled and self._work_on_tasks() and online() and self.ws.load_config().get("learn_files"):
            self._learn_with_claude()   # off unless you turn it on: research uses Claude and the web, not your files
        self._update_counts()
        self._train()

    def run(self, once=False):
        self.say("Autopilot started", "starting")
        while True:
            try:
                self.cycle()
            except Exception as e:  # keep running; launchd would restart us anyway
                self.say(f"Something went wrong, retrying in 2 minutes: {e!r}", "error")
                self._wait(120)
            if once:
                return
