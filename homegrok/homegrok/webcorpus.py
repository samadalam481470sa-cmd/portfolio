"""Web Learner: public text from the outside world for HomeGrok's own model to learn from.

The local model trains only on this public corpus, never on your personal files and never on
Claude's writing (Anthropic's terms don't allow training models on Claude's outputs):
  * Simple English Wikipedia articles (CC BY-SA), fetched a batch at a time from the public API;
  * the text of real job postings, as published on the companies' own job boards (see jobs.py).
The corpus grows every cycle, so the model keeps learning as it goes.
"""
import json
import os
import random
import time
import urllib.parse

from .jobs import _get

WIKI_API = "https://simple.wikipedia.org/w/api.php"
MAX_CORPUS_CHARS = 400_000_000
MIN_TOKENIZER_CHARS = 1_500_000   # build the public tokenizer once the corpus is this big


class PublicCorpus:
    def __init__(self, ws):
        self.dir = ws.root / "public"
        self.dir.mkdir(exist_ok=True)
        self.path = self.dir / "docs.jsonl"
        self.meta_path = self.dir / "meta.json"

    def meta(self):
        try:
            return json.loads(self.meta_path.read_text())
        except (OSError, ValueError):
            return {"docs": 0, "chars": 0, "wiki_titles": 0}

    def _save_meta(self, meta):
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta))
        os.replace(tmp, self.meta_path)

    def append(self, source, texts):
        texts = [t.strip() for t in texts if t and len(t.strip()) > 200]
        meta = self.meta()
        if not texts or meta["chars"] > MAX_CORPUS_CHARS:
            return 0
        with open(self.path, "a", encoding="utf-8") as f:
            for text in texts:
                f.write(json.dumps({"source": source, "text": text}) + "\n")
        meta["docs"] += len(texts)
        meta["chars"] += sum(len(t) for t in texts)
        if source == "wiki":
            meta["wiki_titles"] += len(texts)
        meta["updated"] = time.time()
        self._save_meta(meta)
        return len(texts)


def fetch_wikipedia(n=20):
    """Lead sections of n random Simple English Wikipedia articles."""
    params = {"action": "query", "format": "json", "generator": "random", "grnnamespace": 0, "grnlimit": n,
              "prop": "extracts", "exintro": 1, "explaintext": 1, "exlimit": n, "maxlag": 5}
    code, data = _get(f"{WIKI_API}?{urllib.parse.urlencode(params)}", timeout=20, as_json=True)
    if code != 200 or not isinstance(data, dict):
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    return [f"{p.get('title', '')}\n\n{p.get('extract', '')}" for p in pages.values() if len(p.get("extract", "")) > 300]


def learn_from_web(ws, scout, batches=1, log=print):
    """Add a few Wikipedia batches and any newly verified job postings to the public corpus."""
    corpus = PublicCorpus(ws)
    added = 0
    for _ in range(batches):
        added += corpus.append("wiki", fetch_wikipedia())
        if batches > 1:
            time.sleep(0.5 + random.random())  # be gentle with Wikipedia
    added += corpus.append("job", scout.new_corpus_text())
    if added:
        meta = corpus.meta()
        log(f"Web Learner: added {added} public documents ({meta['chars'] / 1e6:.1f}M characters in total)")
    return added
