"""Support: a searchable index of your documents (BM25-weighted sparse vectors).

The orchestrator uses it to pull the passages from your files that are relevant
to each question, so answers are grounded in your actual data.
"""
import math
import pickle
import re
from collections import Counter, defaultdict

from .config import iter_jsonl

WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = set("""a an and are as at be but by for from has have he her his i if in into is it its
me my not of on or our she so that the their them then there these they this to was we were what
when where which who will with you your""".split())
CHUNK_CHARS, OVERLAP = 1000, 150
K1, B = 1.5, 0.75


def terms(text):
    return [w for w in WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]


def chunk(text):
    if len(text) <= CHUNK_CHARS:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):
            cut = text.rfind("\n", start + CHUNK_CHARS // 2, end)
            end = cut if cut > 0 else end
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return out


class Index:
    def __init__(self):
        self.chunks = []           # [(path, text)]
        self.lengths = []
        self.postings = defaultdict(list)  # term -> [(chunk_id, tf)]

    def add(self, path, text):
        for piece in chunk(text):
            cid = len(self.chunks)
            counts = Counter(terms(piece))
            self.chunks.append((path, piece))
            self.lengths.append(sum(counts.values()))
            for t, tf in counts.items():
                self.postings[t].append((cid, tf))

    def finalize(self):
        n = len(self.chunks)
        self.avg_len = sum(self.lengths) / max(1, n)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}
        self.postings = dict(self.postings)

    def search(self, query, k=4):
        scores = Counter()
        for t in set(terms(query)):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for cid, tf in self.postings[t]:
                norm = tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.lengths[cid] / self.avg_len))
                scores[cid] += idf * norm
        return [{"path": self.chunks[cid][0], "text": self.chunks[cid][1], "score": round(s, 2)}
                for cid, s in scores.most_common(k)]


def build_index(ws, log=print):
    index = Index()
    for doc in iter_jsonl(ws.clean_docs):
        index.add(doc["path"], doc["text"])
    index.finalize()
    with open(ws.index, "wb") as f:
        pickle.dump(index, f)
    log(f"  indexed {len(index.chunks):,} passages, {len(index.idf):,} distinct terms")
    return index


def load_index(ws):
    if not ws.index.exists():
        return None
    with open(ws.index, "rb") as f:
        return pickle.load(f)
