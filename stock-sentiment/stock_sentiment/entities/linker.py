"""Link articles to tickers and find the sentences about each ticker.

Matching rules, strongest first:
  * $AAPL cashtags, "(AAPL)", "(NASDAQ: AAPL)", "NYSE: BA"          -> always trusted
  * bare uppercase ticker "NVDA"                                    -> only 3+ letters and not a common word
  * company name / aliases ("Microsoft", "JPMorgan")                -> case-sensitive, word boundaries
  * aliases that are common words ("Apple", "Visa", "Target")       -> only with finance context in the
                                                                       sentence or a strong match elsewhere
  * source-provided ticker hints with no text match                -> low relevance
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..config import TickerEntry
from ..models import Mention

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'$(])")
CLAUSE_SPLIT = re.compile(r"\s*;\s*|,?\s+(?:while|whereas|but|as)\s+|\s+(?:vs\.?|versus)\s+", re.I)
CONTEXT = re.compile(
    r"\b(stocks?|shares?|investors?|earnings|revenue|profit|sales|guidance|analysts?|price target|upgrade[sd]?|"
    r"downgrade[sd]?|outperform|underperform|valuation|market cap|dividend|buyback|quarter(ly)?|fiscal|CEO|CFO|"
    r"Inc\b|Corp\b|NASDAQ|Nasdaq|NYSE|S&P|Dow|Wall Street|rall(y|ies|ied)|slump(s|ed)?|surge[sd]?|plunge[sd]?|"
    r"tumble[sd]?|soar(s|ed)?|bull(ish)?|bear(ish)?|gains?|loss(es)?|rise[sn]?|rose|fall(s|en)?|fell|drops?|jumps?|"
    r"slides?|record high|trillion|billion|market|tech|iPhone|iPad|Mac|AWS|Prime)\b|\$\d", re.I)
LOCATION_RELEVANCE = {"headline": 1.0, "lead": 0.7, "body": 0.4, "hint": 0.25}


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text or "") if s.strip()]


@dataclass
class _Patterns:
    entry: TickerEntry
    strong: re.Pattern
    bare: re.Pattern | None
    names: re.Pattern | None
    needs_context: bool


class Linker:
    def __init__(self, universe: list[TickerEntry], ambiguous_tickers: list[str]):
        ambiguous = {t.upper() for t in ambiguous_tickers}
        self.universe = {e.ticker: e for e in universe}
        self._patterns: list[_Patterns] = []
        for e in universe:
            t = re.escape(e.ticker)
            strong = re.compile(
                rf"\${t}\b|\((?:[A-Za-z]+\s*:\s*)?{t}\)|\b(?:NYSE|NASDAQ|Nasdaq|NYSEARCA|AMEX)\s*:\s*{t}\b")
            bare = None
            if len(e.ticker) >= 3 and e.ticker not in ambiguous:
                bare = re.compile(rf"(?<![\w$]){t}(?![\w])")
            names = sorted({e.name, *e.aliases} - {""}, key=len, reverse=True)
            # Aliases that are themselves the ticker (e.g. "AMD") are treated like the bare ticker.
            names_re = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w])") if names else None
            self._patterns.append(_Patterns(e, strong, bare, names_re, e.context_required))

    # ---- matching ---------------------------------------------------------
    def _matches(self, p: _Patterns, sentence: str, strong_elsewhere: bool) -> bool:
        if p.strong.search(sentence):
            return True
        if p.bare and p.bare.search(sentence):
            return True
        if p.names and p.names.search(sentence):
            return not p.needs_context or strong_elsewhere or bool(CONTEXT.search(sentence))
        return False

    def _segments(self, title: str, summary: str, body: str) -> list[tuple[str, str]]:
        segs = [("headline", title)]
        rest = split_sentences(" ".join(x for x in (summary, body) if x))
        segs += [("lead" if i == 0 else "body", s) for i, s in enumerate(rest)]
        return segs

    def link(self, article_id: str, title: str, summary: str = "", body: str = "",
             hints: list[str] | None = None) -> list[Mention]:
        segments = self._segments(title, summary, body)
        full_text = " ".join(s for _, s in segments)
        found: dict[str, tuple[float, str]] = {}
        for p in self._patterns:
            strong_elsewhere = bool(p.strong.search(full_text) or (p.bare and p.bare.search(full_text)))
            hits = [loc for loc, s in segments if self._matches(p, s, strong_elsewhere)]
            if hits:
                best = max(hits, key=lambda loc: LOCATION_RELEVANCE[loc])
                # Repeated mentions mean the article is more about this company.
                rel = min(1.0, LOCATION_RELEVANCE[best] + 0.05 * (len(hits) - 1))
                found[p.entry.ticker] = (rel, best)
        for h in hints or []:
            if h in self.universe:
                if h in found:
                    rel, loc = found[h]
                    found[h] = (min(1.0, rel + 0.1), loc)
                else:
                    found[h] = (LOCATION_RELEVANCE["hint"], "hint")
        # Roundup articles that mention many companies say little about any single one.
        crowd = min(1.0, 1.5 / math.sqrt(len(found))) if found else 1.0
        return [Mention(article_id, t, round(rel * crowd, 4), loc) for t, (rel, loc) in found.items()]

    def sentences_for(self, ticker: str, title: str, summary: str = "", body: str = "") -> list[tuple[str, float]]:
        """Sentences about `ticker` with weights (headline counts double). Falls back to the headline,
        which is right for hint-only mentions (the source says the article is about this ticker)."""
        p = next((p for p in self._patterns if p.entry.ticker == ticker), None)
        segments = self._segments(title, summary, body)
        if p is None:
            return [(title, 1.0)]
        full_text = " ".join(s for _, s in segments)
        strong_elsewhere = bool(p.strong.search(full_text) or (p.bare and p.bare.search(full_text)))
        out = []
        for loc, s in segments:
            if not self._matches(p, s, strong_elsewhere):
                continue
            # "Nvidia soars while Intel slumps": keep only the clause about this ticker when we can.
            clauses = [c for c in CLAUSE_SPLIT.split(s) if c and self._matches(p, c, True)]
            text = clauses[0] if len(clauses) == 1 and len(CLAUSE_SPLIT.split(s)) > 1 else s
            out.append((text, 2.0 if loc == "headline" else 1.0))
        return out or [(title, 1.0)]
