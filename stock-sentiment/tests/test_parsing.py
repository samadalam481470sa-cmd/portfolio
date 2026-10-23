from datetime import datetime, timezone
from pathlib import Path

from stock_sentiment.models import RawArticle
from stock_sentiment.parse.dedupe import is_rehash
from stock_sentiment.parse.html import extract_article_text
from stock_sentiment.parse.normalize import EASTERN, canonical_url, normalize, parse_date, title_hash
from stock_sentiment.parse.rss import parse_feed
from stock_sentiment.sources.finviz import parse_news_table

FIX = Path(__file__).parent / "fixtures"


def test_parse_nasdaq_rss_extracts_items_and_ticker_tags():
    items = parse_feed((FIX / "nasdaq_aapl.xml").read_text())
    assert len(items) == 2
    assert items[0].title == "The AI Rally, Mega-Cap Dominance & What Comes Next"
    assert items[0].publisher == "Zacks"
    assert items[0].extra["nasdaq:tickers"] == "AAPL,MSFT,MU,NVDA,QQQ"
    assert items[1].summary == "Apple reported record revenue. Shares rose 4% after hours."


def test_parse_edgar_atom():
    items = parse_feed((FIX / "edgar_aapl.xml").read_text())
    assert len(items) == 1
    assert items[0].extra["items-desc"] == "items 2.02 and 9.01"
    assert items[0].link.endswith("-index.htm")
    assert parse_date(items[0].published) == datetime(2026, 7, 30, 20, 30, 28, tzinfo=timezone.utc)


def test_finviz_dates_carry_forward_and_use_eastern_time():
    now = datetime(2026, 10, 12, 20, 0, tzinfo=EASTERN)
    rows = parse_news_table((FIX / "finviz_aapl.html").read_text(), "AAPL", now=now)
    assert [r.publisher for r in rows] == ["Reuters", "Zacks", "Bloomberg", "MarketWatch"]
    assert rows[0].published_at == datetime(2026, 10, 12, 18, 2, tzinfo=EASTERN)
    assert rows[1].published_at == datetime(2026, 10, 12, 16, 57, tzinfo=EASTERN)  # same day as row above
    assert rows[3].published_at == datetime(2026, 10, 9, 8, 0, tzinfo=EASTERN)    # carries Oct-09
    assert rows[1].url == "https://finviz.com/news/401460/the-ai-rally"
    assert all(r.ticker_hints == ["AAPL"] for r in rows)


def test_canonical_url_strips_tracking_params():
    assert canonical_url("https://www.Example.com/a/b/?utm_source=x&id=5&mod=rss") == "https://example.com/a/b?id=5"


def test_normalize_handles_publisher_suffix_dates_and_future():
    now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    a = normalize(RawArticle(source="google_news", url="https://x.com/1", title="Apple soars - Reuters",
                             publisher="Reuters", published_at="Tue, 13 Oct 2026 02:00:00 GMT"), now=now)
    assert a.title == "Apple soars"
    assert a.published_at == now  # future timestamps are clamped
    assert normalize(RawArticle(source="s", url="", title="x")) is None


def test_title_hash_ignores_case_and_punctuation():
    assert title_hash("Apple Soars!") == title_hash("apple  soars")


def test_rehash_detection():
    assert is_rehash("Apple stock jumps after earnings beat", ["Apple stock jumps after earnings beat estimates"], 88)
    assert not is_rehash("Apple faces EU antitrust probe", ["Apple stock jumps after earnings beat"], 88)


def test_extract_article_text_skips_boilerplate():
    html = """<html><body><nav><p>Home News Markets Subscribe to our newsletter today now</p></nav>
    <article><p>Apple reported quarterly revenue that beat analyst expectations by a wide margin.</p>
    <div class="related"><p>Related: other stories you might like to read today here</p></div>
    <p>Short.</p></article></body></html>"""
    assert extract_article_text(html) == "Apple reported quarterly revenue that beat analyst expectations by a wide margin."
