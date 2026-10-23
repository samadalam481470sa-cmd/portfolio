"""Tokenizer: text to numbers.

A byte-level BPE tokenizer trained on *your* files, on *your* computer, so its
vocabulary is shaped by the words you actually use.
"""
import heapq
import json
import re
from collections import Counter, defaultdict

PRETOKENIZE = re.compile(r"""'s|'t|'re|'ve|'m|'ll|'d| ?[A-Za-z]+| ?\d{1,3}| ?[^\sA-Za-z\d]+|\s+(?!\S)|\s+""")
SPECIAL_TOKENS = ["<|endoftext|>"]


def _merge(word, pair, new_id):
    out, i = [], 0
    while i < len(word):
        if i < len(word) - 1 and word[i] == pair[0] and word[i + 1] == pair[1]:
            out.append(new_id)
            i += 2
        else:
            out.append(word[i])
            i += 1
    return out


class Tokenizer:
    def __init__(self, merges, specials):
        self.merges = {tuple(p): i for p, i in merges}          # (a, b) -> new id
        self.vocab = {i: bytes([i]) for i in range(256)}
        for (a, b), i in sorted(self.merges.items(), key=lambda kv: kv[1]):
            self.vocab[i] = self.vocab[a] + self.vocab[b]
        self.specials = dict(specials)
        for s, i in self.specials.items():
            self.vocab[i] = s.encode()
        self.inverse_specials = {i: s for s, i in self.specials.items()}
        self.eot = self.specials["<|endoftext|>"]
        self._special_re = re.compile("(" + "|".join(re.escape(s) for s in self.specials) + ")")
        self._cache = {}

    @property
    def vocab_size(self):
        return max(self.vocab) + 1

    # -- training ------------------------------------------------------------
    @classmethod
    def train(cls, texts, vocab_size=4096, log=print):
        counts = Counter()
        for text in texts:
            counts.update(PRETOKENIZE.findall(text))
        words = [list(w.encode("utf-8")) for w in counts]
        freqs = list(counts.values())
        log(f"  {len(words):,} unique chunks")

        pair_counts = Counter()
        where = defaultdict(set)
        for wi, w in enumerate(words):
            for p in zip(w, w[1:]):
                pair_counts[p] += freqs[wi]
                where[p].add(wi)
        heap = [(-c, p) for p, c in pair_counts.items()]
        heapq.heapify(heap)

        merges = []
        n_merges = vocab_size - 256 - len(SPECIAL_TOKENS)
        while len(merges) < n_merges and heap:
            neg, pair = heapq.heappop(heap)
            if pair_counts.get(pair, 0) != -neg:
                continue  # stale heap entry
            if -neg < 2:
                break
            new_id = 256 + len(merges)
            merges.append((pair, new_id))
            changed = set()
            for wi in where.pop(pair, ()):
                w, f = words[wi], freqs[wi]
                if len(w) < 2:
                    continue
                for p in zip(w, w[1:]):
                    pair_counts[p] -= f
                    changed.add(p)
                w = _merge(w, pair, new_id)
                words[wi] = w
                for p in zip(w, w[1:]):
                    pair_counts[p] += f
                    where[p].add(wi)
                    changed.add(p)
            for p in changed:
                c = pair_counts.get(p, 0)
                if c > 0:
                    heapq.heappush(heap, (-c, p))
                else:
                    pair_counts.pop(p, None)
            if len(merges) % 500 == 0:
                log(f"  {len(merges)}/{n_merges} merges")

        base = 256 + len(merges)
        specials = {s: base + i for i, s in enumerate(SPECIAL_TOKENS)}
        return cls(merges, specials)

    # -- encode / decode ----------------------------------------------------
    def _encode_chunk(self, chunk):
        cached = self._cache.get(chunk)
        if cached is not None:
            return cached
        ids = list(chunk.encode("utf-8"))
        while len(ids) >= 2:
            pair = min(zip(ids, ids[1:]), key=lambda p: self.merges.get(p, float("inf")))
            if pair not in self.merges:
                break
            ids = _merge(ids, pair, self.merges[pair])
        if len(self._cache) < 500_000:
            self._cache[chunk] = ids
        return ids

    def encode(self, text, allow_special=False):
        ids = []
        parts = self._special_re.split(text) if allow_special else [text]
        for part in parts:
            if allow_special and part in self.specials:
                ids.append(self.specials[part])
                continue
            for chunk in PRETOKENIZE.findall(part):
                ids.extend(self._encode_chunk(chunk))
        return ids

    def decode(self, ids):
        out = b"".join(self.vocab.get(i, b"") for i in ids if i not in self.inverse_specials)
        return out.decode("utf-8", errors="replace")

    # -- storage --------------------------------------------------------------
    def save(self, path):
        merges = [[list(p), i] for p, i in sorted(self.merges.items(), key=lambda kv: kv[1])]
        path.write_text(json.dumps({"merges": merges, "specials": self.specials}))

    @classmethod
    def load(cls, path):
        data = json.loads(path.read_text())
        return cls([(tuple(p), i) for p, i in data["merges"]], data["specials"])


def train_tokenizer(ws, vocab_size=4096, max_chars=15_000_000, log=print):
    """Learn the vocabulary from the public corpus the local model trains on (see webcorpus.py)."""
    from .config import iter_jsonl

    def texts():
        seen = 0
        for doc in iter_jsonl(ws.public_docs):
            yield doc["text"]
            seen += len(doc["text"])
            if seen >= max_chars:
                return

    tok = Tokenizer.train(texts(), vocab_size=vocab_size, log=log)
    tok.save(ws.tokenizer)
    log(f"  tokenizer saved: {tok.vocab_size} tokens")
    return tok
