"""The stock universe: tickers, company names and aliases.

The default universe lives in config.yaml. `load_sp500()` scrapes the S&P 500 constituents table from
Wikipedia with BeautifulSoup and derives aliases from company names.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..config import TickerEntry
from ..fetch.http import HttpClient

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CORP_SUFFIX = re.compile(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Co\.?|Company|Ltd\.?|plc|PLC|N\.V\.|"
                         r"S\.A\.|Holdings?|Group|Class [A-C]|& Co\.?|L\.P\.)$")
# Short names that collide with ordinary words; these need finance context to count.
COMMON_WORD_NAMES = {"apple", "target", "visa", "oracle", "gap", "ball", "match", "progressive", "public storage",
                     "best buy", "general", "southern", "american", "united", "news", "fox", "corning",
                     "amazon", "coke", "chase", "meta", "block", "edison", "carrier", "dollar general"}


def short_name(name: str) -> str:
    prev = None
    while prev != name:
        prev, name = name, CORP_SUFFIX.sub("", name).strip()
    return name


def entry_for(ticker: str, name: str) -> TickerEntry:
    alias = short_name(name)
    aliases = [alias] if alias and alias != name else []
    return TickerEntry(ticker=ticker, name=name, aliases=aliases,
                       context_required=alias.lower() in COMMON_WORD_NAMES)


def load_sp500(http: HttpClient) -> list[TickerEntry]:
    resp = http.get(SP500_URL, conditional=False)
    soup = BeautifulSoup(resp.text or "", "lxml")
    table = soup.find("table", id="constituents")
    if table is None:
        raise RuntimeError("S&P 500 table not found on Wikipedia page")
    out = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        ticker = cells[0].get_text(strip=True).replace(".", "-")  # BRK.B -> BRK-B (Yahoo style)
        out.append(entry_for(ticker, cells[1].get_text(strip=True)))
    return out
