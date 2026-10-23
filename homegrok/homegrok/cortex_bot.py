"""The Cortex: HomeGrok's continual-learning memory, built on the relearn library.

It learns only from the PUBLIC corpus (Wikipedia and job postings the Web Learner gathered),
never from your personal files and never from Claude's replies. It runs offline: it makes no
web requests of its own. Its state is saved to the workspace so it survives every restart.
"""
import json
import os
import threading
from pathlib import Path

from .config import iter_jsonl

_lock = threading.Lock()


class PublicCortex:
    def __init__(self, ws):
        self.ws = ws
        self.model_path = ws.root / "cortex.npz"
        self.meta_path = ws.root / "cortex_meta.json"
        self.cortex = None

    def _load(self):
        if self.cortex is None:
            from .relearn import Cortex, CortexConfig
            cfg = CortexConfig(online=False)
            if self.model_path.exists():
                self.cortex = Cortex.load(str(self.model_path), cfg=cfg)
            else:
                self.cortex = Cortex(cfg)
        return self.cortex

    def meta(self):
        try:
            return json.loads(self.meta_path.read_text())
        except (OSError, ValueError):
            return {"docs_learned": 0, "steps": 0}

    def learn_new(self, max_docs=40):
        """Learn from public documents not yet seen. Returns how many were learned."""
        with _lock:
            corpus = self.ws.public_docs
            if not corpus.exists():
                return 0
            meta = self.meta()
            done = meta["docs_learned"]
            texts = []
            for i, doc in enumerate(iter_jsonl(corpus)):
                if i < done:
                    continue
                texts.append(doc["text"][:4000])
                if len(texts) >= max_docs:
                    break
            if not texts:
                return 0
            cortex = self._load()
            for text in texts:
                cortex.learn_text(text, source="wikipedia", title="public text")
            cortex.relearn(steps=min(8, cortex.cfg.sleep_steps))   # consolidate what was learned
            cortex.reinforce()
            tmp = self.model_path.with_name("cortex.tmp.npz")
            cortex.save(str(tmp))
            os.replace(tmp, self.model_path)
            meta = {"docs_learned": done + len(texts), "steps": cortex.step_i}
            self.meta_path.write_text(json.dumps(meta))
            return len(texts)

    def recall(self, text, k=3):
        """Public memories closest to a question (used by chat to find related public knowledge)."""
        with _lock:
            if not self.model_path.exists():
                return []
            return self._load().recall(text, k=k)

    def learn_one(self, text, title="web"):
        """Learn one online document (already checked for permission and capped by the caller)."""
        with _lock:
            cortex = self._load()
            cortex.learn_text(text[:4000], source="wikipedia", title=title)
            cortex.reinforce()
            tmp = self.model_path.with_name("cortex.tmp.npz")
            cortex.save(str(tmp))
            os.replace(tmp, self.model_path)
