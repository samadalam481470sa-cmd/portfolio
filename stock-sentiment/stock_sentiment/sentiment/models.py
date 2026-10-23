"""Swappable sentiment scorers. All return SentimentScore with compound in [-1, 1]."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..models import SentimentScore

log = logging.getLogger(__name__)


class Scorer(ABC):
    name: str

    @abstractmethod
    def score_batch(self, texts: list[str]) -> list[SentimentScore]: ...


class VaderScorer(Scorer):
    """Fast lexicon baseline. Tuned for social media, so it misreads finance phrasing ("beat", "short")."""

    name = "vader"

    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self._analyzer = SentimentIntensityAnalyzer()

    def score_batch(self, texts: list[str]) -> list[SentimentScore]:
        out = []
        for t in texts:
            s = self._analyzer.polarity_scores(t)
            out.append(SentimentScore(pos=s["pos"], neg=s["neg"], neu=s["neu"], compound=s["compound"]))
        return out


class FinBertScorer(Scorer):
    """ProsusAI/finbert: BERT fine-tuned on financial news. ~440MB download on first use; runs on CPU."""

    name = "finbert"
    MODEL_ID = "ProsusAI/finbert"

    def __init__(self, batch_size: int = 16):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.batch_size = batch_size
        self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.MODEL_ID)
        self.model.eval()
        self.device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        labels = {v.lower(): k for k, v in self.model.config.id2label.items()}
        self._idx = (labels["positive"], labels["negative"], labels["neutral"])

    def score_batch(self, texts: list[str]) -> list[SentimentScore]:
        out: list[SentimentScore] = []
        pi, ni, ui = self._idx
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i:i + self.batch_size]
            enc = self.tokenizer(chunk, padding=True, truncation=True, max_length=128, return_tensors="pt")
            enc = {k: v.to(self.device) for k, v in enc.items()}
            with self._torch.no_grad():
                probs = self._torch.softmax(self.model(**enc).logits, dim=-1).cpu().tolist()
            for p in probs:
                out.append(SentimentScore(pos=p[pi], neg=p[ni], neu=p[ui], compound=p[pi] - p[ni]))
        return out


def make_scorer(name: str, batch_size: int = 16) -> Scorer:
    if name == "vader":
        return VaderScorer()
    if name == "finbert":
        try:
            return FinBertScorer(batch_size)
        except Exception as e:  # missing torch/transformers, no network for the first download, etc.
            log.warning("FinBERT unavailable (%s); falling back to VADER", e)
            return VaderScorer()
    raise ValueError(f"unknown sentiment model {name!r}")
