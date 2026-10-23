"""Tests for news RSS parsing."""

from market_agent.intelligence.news_fetcher import _parse_rss

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Apple stock surges on earnings beat - Reuters</title>
      <link>https://example.com/1</link>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
      <source>Reuters</source>
    </item>
    <item>
      <title>Tesla misses delivery targets - Bloomberg</title>
      <link>https://example.com/2</link>
      <pubDate>Mon, 01 Jan 2024 11:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


def test_parse_rss():
    items = _parse_rss(SAMPLE_RSS, limit=5)
    assert len(items) == 2
    assert "Apple" in items[0].title
    assert items[0].source == "Reuters"
