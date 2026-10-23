"""Web research via DuckDuckGo Instant Answer API (no API key required)."""

from __future__ import annotations

import httpx

DDG_API = "https://api.duckduckgo.com/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketAgent/1.0)"}


class WebResearcher:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0, headers=HEADERS)

    async def close(self) -> None:
        await self._client.aclose()

    async def research(self, query: str, max_snippets: int = 5) -> list[str]:
        """Gather real-world context snippets about a topic or stock."""
        snippets: list[str] = []

        # DuckDuckGo instant answer
        ddg = await self._ddg_search(query)
        snippets.extend(ddg[:max_snippets])

        # Wikipedia summary via DDG
        wiki_query = f"{query} stock company"
        wiki = await self._ddg_search(wiki_query)
        for s in wiki:
            if s not in snippets:
                snippets.append(s)

        return snippets[:max_snippets]

    async def research_symbol(self, symbol: str) -> list[str]:
        return await self.research(f"{symbol} stock news analysis outlook", max_snippets=6)

    async def _ddg_search(self, query: str) -> list[str]:
        resp = await self._client.get(
            DDG_API,
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        snippets: list[str] = []

        if data.get("AbstractText"):
            snippets.append(data["AbstractText"])
        if data.get("Answer"):
            snippets.append(f"Answer: {data['Answer']}")

        for topic in data.get("RelatedTopics", [])[:4]:
            if isinstance(topic, dict) and topic.get("Text"):
                snippets.append(topic["Text"])

        return snippets
