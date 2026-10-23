import pytest

from stock_sentiment.config import TickerEntry
from stock_sentiment.entities.linker import Linker
from stock_sentiment.entities.universe import entry_for, short_name

UNIVERSE = [
    TickerEntry(ticker="AAPL", name="Apple Inc.", aliases=["Apple"], context_required=True),
    TickerEntry(ticker="NVDA", name="NVIDIA Corporation", aliases=["Nvidia"]),
    TickerEntry(ticker="INTC", name="Intel Corporation", aliases=["Intel"]),
    TickerEntry(ticker="IT", name="Gartner, Inc.", aliases=["Gartner"]),
    TickerEntry(ticker="F", name="Ford Motor Company", aliases=["Ford Motor"]),
]


@pytest.fixture
def linker():
    return Linker(UNIVERSE, ambiguous_tickers=["IT", "F"])


def tickers(mentions):
    return {m.ticker: m for m in mentions}


def test_word_tickers_need_strong_form(linker):
    assert "IT" not in tickers(linker.link("1", "IT spending is expected to rise next year"))
    assert "IT" in tickers(linker.link("2", "Gartner (NYSE: IT) raises outlook"))
    assert "F" not in tickers(linker.link("3", "Stocks get an F for October"))
    assert "F" in tickers(linker.link("4", "$F shares slide on recall"))


def test_common_word_alias_needs_finance_context(linker):
    assert "AAPL" not in tickers(linker.link("1", "Apple orchards report a bumper harvest"))
    assert "AAPL" in tickers(linker.link("2", "Apple shares hit a record high"))


def test_bare_ticker_and_relevance_by_location(linker):
    m = tickers(linker.link("1", "Chip stocks mixed", summary="Analysts were upbeat. NVDA closed higher."))
    assert m["NVDA"].location == "body"
    m = tickers(linker.link("2", "Nvidia unveils new chip"))
    assert m["NVDA"].location == "headline" and m["NVDA"].relevance == 1.0


def test_hints_add_low_relevance_mentions(linker):
    m = tickers(linker.link("1", "Markets slide on rate fears", hints=["NVDA", "ZZZZ"]))
    assert set(m) == {"NVDA"}
    assert m["NVDA"].location == "hint" and m["NVDA"].relevance < 0.5


def test_roundups_get_lower_relevance(linker):
    m = tickers(linker.link("1", "Nvidia, Intel, Apple stock and Gartner (IT) shares move"))
    assert len(m) == 4
    assert all(x.relevance < 1.0 for x in m.values())


def test_clause_attribution(linker):
    title = "Nvidia soars while Intel slumps"
    assert linker.sentences_for("NVDA", title) == [("Nvidia soars", 2.0)]
    assert linker.sentences_for("INTC", title) == [("Intel slumps", 2.0)]


def test_sentences_fall_back_to_headline_for_hints(linker):
    assert linker.sentences_for("NVDA", "Markets slide") == [("Markets slide", 1.0)]


def test_universe_name_helpers():
    assert short_name("Apple Inc.") == "Apple"
    assert short_name("JPMorgan Chase & Co.") == "JPMorgan Chase"
    assert entry_for("TGT", "Target Corporation").context_required
    assert not entry_for("MSFT", "Microsoft Corporation").context_required
