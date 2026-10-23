"""Score each (article, ticker) pair from the sentences that are about that ticker, so
"Nvidia soars while Intel slumps" is positive for NVDA and negative for INTC."""
from __future__ import annotations

from ..entities.linker import Linker
from ..models import SentimentScore
from .models import Scorer


def score_mentions(scorer: Scorer, linker: Linker, rows: list[dict]) -> list[SentimentScore]:
    """rows: dicts with ticker, title, summary, body. Each unique sentence is scored once."""
    per_row = [linker.sentences_for(r["ticker"], r["title"], r["summary"] or "", r["body"] or "") for r in rows]
    unique = sorted({s for sents in per_row for s, _ in sents})
    scores = dict(zip(unique, scorer.score_batch(unique))) if unique else {}
    out = []
    for sents in per_row:
        total = sum(w for _, w in sents)
        agg = {k: sum(getattr(scores[s], k) * w for s, w in sents) / total for k in ("pos", "neg", "neu", "compound")}
        out.append(SentimentScore(**agg))
    return out
